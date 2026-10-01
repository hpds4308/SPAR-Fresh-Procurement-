"""
Auto-submission of missed branch orders.

Once the daily branch cutoff (settings.BRANCH_ORDER_DEADLINE) has passed,
any active branch that hasn't submitted today's order gets one submitted
for it, so a forgotten order never means an empty delivery:

- If the branch saved a DRAFT but never pressed Submit, that draft is
  submitted as-is — it's the branch's own, most recent intent, and far
  closer to what they want than a week-old copy.
- Otherwise the weekly fallback: the branch's own order from the same
  weekday one week back (order_date - 7), then two weeks back
  (order_date - 14), and so on, up to settings.AUTO_SUBMIT_LOOKBACK_WEEKS.
  The first eligible one wins — never an older order over a more recent
  one, and never a different weekday or a different branch. Its product
  lines and ordered quantities are copied (products since deactivated
  are dropped); the new order gets today's own delivery date, never the
  historical one.
- Nothing eligible in the lookback window -> nothing is created. A
  MissedOrderNotice ("No Previous Order Found") is recorded instead, so
  Admin is told the branch has no order.

"Eligible" = SUBMITTED/ASSIGNED/CONFIRMED with at least one line for a
still-active product. Drafts (never sent) and orders with nothing left to
copy are skipped and the search moves one more week back.

A branch Admin granted a late-submission exception for today is skipped —
Admin has explicitly given them more time. An order the branch (or Admin)
already submitted is never touched.

Every auto-submitted order is flagged (Order.auto_submitted) and stays
"unreviewed" until Admin acknowledges it, which is what drives the badge
and banner on the Admin dashboard. Runs from a background thread in the
API process (see start_scheduler), once a minute; each run is idempotent
and a no-op before the cutoff or once every branch has an order.
"""
import logging
import threading
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.config import settings
from app.models.branch import Branch
from app.models.missed_order_notice import MissedOrderNotice
from app.models.order import Order, OrderLine
from app.models.product import Product
from app.models.user import User
from app.services import settings_service
from app.services.order_service import BUSINESS_TZ, _has_deadline_exception, _parse_cutoff, get_order_window

logger = logging.getLogger(__name__)

# Stored in Order.auto_submit_source. "LAST_WEEK" is kept as the stored
# value for the weekly fallback (whichever week back it found) so rows
# written before the multi-week search existed keep their meaning; see
# weeks_back() for how far back the source was. "LATEST" only exists on
# rows from the short-lived any-weekday fallback this replaced.
SOURCE_PREVIOUS_WEEK = "LAST_WEEK"
SOURCE_LATEST_LEGACY = "LATEST"
SOURCE_DRAFT = "DRAFT"

# Statuses a branch order can be copied from. An allowlist rather than
# "anything but DRAFT", so a status added later (e.g. cancelled) is never
# copied by accident.
ELIGIBLE_SOURCE_STATUSES = ("SUBMITTED", "ASSIGNED", "CONFIRMED")

# Arbitrary constant key for pg_try_advisory_lock, so two API processes
# (e.g. a redeploy overlapping the old container) never run the same pass
# at once. uq_orders_branch_order_date would still stop a duplicate order,
# but this keeps a second pass from even trying.
_ADVISORY_LOCK_KEY = 725_014_001


def fallback_source_dates(order_date: date, max_weeks: int) -> list[date]:
    """The order dates to try as a source for order_date, most recent first: the same weekday
    1, 2, ... max_weeks weeks earlier. Plain 7-day steps, so month/year ends and leap days need
    no special handling."""
    return [order_date - timedelta(days=7 * n) for n in range(1, max_weeks + 1)]


def weeks_back(order: Order, source_order_date: date | None) -> int | None:
    """How many weeks back the weekly fallback found this order's source (1 = previous week)."""
    if order.auto_submit_source != SOURCE_PREVIOUS_WEEK or source_order_date is None:
        return None
    return (order.order_date - source_order_date).days // 7


@contextmanager
def _single_pass_lock(db: Session):
    """
    Yields True if this process may run the pass. Held on its own connection with a session-level
    advisory lock, so it lasts the whole pass — the pass commits once per branch, and a
    transaction-scoped lock would be released at the first of those commits.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql":
        yield True
        return
    engine = getattr(bind, "engine", bind)  # a Session bound to a Connection (tests) -> its Engine
    with engine.connect() as conn:
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY}).scalar()
        try:
            yield bool(got)
        finally:
            if got:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})
            conn.commit()


def auto_submit_missed_orders(db: Session, now: datetime | None = None) -> list[Order]:
    """One pass: submits today's order for every branch that missed the cutoff. Returns the orders
    it submitted (empty before the cutoff, or when every branch already has one)."""
    now = now.astimezone(BUSINESS_TZ) if now else datetime.now(BUSINESS_TZ)
    cutoff = _parse_cutoff(settings_service.get_setting(db, settings_service.BRANCH_ORDER_DEADLINE))
    if now.time() < cutoff:
        return []

    today = now.date()
    # The current ordering schedule's delivery date for an order placed today — never the
    # source order's own (by now long past) delivery date.
    delivery_date = get_order_window(db, now=now).delivery_date
    max_weeks = settings.AUTO_SUBMIT_LOOKBACK_WEEKS

    submitted: list[Order] = []
    with _single_pass_lock(db) as got_lock:
        if not got_lock:
            return []
        for branch in db.query(Branch).filter(Branch.status == "ACTIVE").order_by(Branch.id).all():
            try:
                order = _process_branch(db, branch, today, delivery_date, max_weeks)
            except IntegrityError:
                # The branch (or Admin) created today's order between our lookup and commit —
                # theirs wins, and nothing from this branch's attempt is kept.
                db.rollback()
                continue
            if order is not None:
                submitted.append(order)
    db.commit()
    return submitted


def _process_branch(db: Session, branch: Branch, today: date, delivery_date: date, max_weeks: int) -> Order | None:
    """Handles one branch in its own transaction (the order, its lines and its audit row commit
    together, via write_audit_log's commit). Returns the order it submitted, if any."""
    existing = db.query(Order).filter(Order.branch_id == branch.id, Order.order_date == today).first()
    if existing and existing.status != "DRAFT":
        return None  # already submitted by the branch or Admin — never touched
    if _has_deadline_exception(db, branch.id, today):
        return None

    if existing and _submit_draft(db, existing):
        order, how, line_count = existing, "the branch's unsent draft", _line_count(db, existing)
    else:
        found = _find_fallback_source(db, branch.id, today, max_weeks)
        if found is None:
            _record_missed(db, branch, today, max_weeks)
            return None
        source, source_lines = found
        if existing:
            # A DRAFT with no lines — the source's lines take its place under the same row.
            db.delete(existing)
            db.flush()
        order = _create_from_source(db, branch, today, delivery_date, source, source_lines)
        line_count = _line_count(db, order)
        n = (today - source.order_date).days // 7
        how = (
            f"the order from {source.order_date.isoformat()} "
            f"({n} week{'s' if n != 1 else ''} back, same weekday)"
        )

    write_audit_log(  # commits the order and this row together
        db,
        user_id=None,
        role="SYSTEM",
        action="ORDER_AUTO_SUBMITTED",
        entity_type="order",
        entity_id=order.id,
        description=(
            f"'{branch.branch_name}' submitted nothing by the cutoff — auto-submitted {how}, "
            f"{line_count} product(s), order date {today.isoformat()}, "
            f"delivery {order.delivery_date.isoformat()}."
        ),
    )
    db.refresh(order)
    return order


def _line_count(db: Session, order: Order) -> int:
    return db.query(OrderLine).filter(OrderLine.order_id == order.id).count()


def _submit_draft(db: Session, draft: Order) -> bool:
    """Submits the branch's own unsent draft as-is. False if it has no lines to submit."""
    if not _line_count(db, draft):
        return False
    draft.status = "SUBMITTED"
    draft.auto_submitted = True
    draft.auto_submit_source = SOURCE_DRAFT
    db.flush()
    return True


def _active_lines(db: Session, order: Order) -> list[OrderLine]:
    return (
        db.query(OrderLine)
        .join(Product, Product.id == OrderLine.product_id)
        .filter(OrderLine.order_id == order.id, Product.status == "ACTIVE")
        .order_by(OrderLine.id)
        .all()
    )


def _find_fallback_source(
    db: Session, branch_id: int, order_date: date, max_weeks: int
) -> tuple[Order, list[OrderLine]] | None:
    """The weekly fallback: this branch's eligible order on the same weekday 1, 2, ... max_weeks
    weeks back — the most recent one found wins. Returns it with the lines to copy, or None."""
    candidates = fallback_source_dates(order_date, max_weeks)
    by_date = {
        o.order_date: o
        for o in db.query(Order)
        .filter(
            Order.branch_id == branch_id,
            Order.order_date.in_(candidates),
            Order.status.in_(ELIGIBLE_SOURCE_STATUSES),
        )
        .all()
    }
    for candidate in candidates:  # most recent first — never skip a newer eligible order
        source = by_date.get(candidate)
        if source is None:
            continue
        lines = _active_lines(db, source)
        if lines:
            return source, lines
    return None


def _create_from_source(
    db: Session,
    branch: Branch,
    today: date,
    delivery_date: date,
    source: Order,
    source_lines: list[OrderLine],
) -> Order:
    # submitted_by is NOT NULL — attribute it to the branch's own account (the order is on their
    # behalf); the auto_submitted flag is what tells everyone the system actually placed it.
    branch_user = (
        db.query(User).filter(User.branch_id == branch.id, User.is_active.is_(True)).order_by(User.id).first()
    )
    order = Order(
        branch_id=branch.id,
        submitted_by=branch_user.id if branch_user else source.submitted_by,
        order_date=today,
        delivery_date=delivery_date,
        status="SUBMITTED",
        notes=source.notes,
        auto_submitted=True,
        auto_submit_source=SOURCE_PREVIOUS_WEEK,
        auto_source_order_id=source.id,
    )
    db.add(order)
    db.flush()  # raises IntegrityError right here if today's order appeared meanwhile

    # One line per product. A valid order never repeats a product, but a legacy row might; its
    # quantities are summed, the same way the order matrix already totals them.
    merged: dict[int, OrderLine] = {}
    for ln in source_lines:
        if ln.product_id in merged:
            merged[ln.product_id].quantity = float(merged[ln.product_id].quantity) + float(ln.quantity)
            continue
        merged[ln.product_id] = OrderLine(
            order_id=order.id,
            product_id=ln.product_id,
            quantity=ln.quantity,
            unit_code=ln.unit_code,
            notes=ln.notes,
        )
    db.add_all(merged.values())
    db.flush()
    return order


def _record_missed(db: Session, branch: Branch, order_date: date, max_weeks: int) -> None:
    """Nothing to auto-submit for this branch — leave Admin a notice (once per branch per date)."""
    exists = (
        db.query(MissedOrderNotice)
        .filter(MissedOrderNotice.branch_id == branch.id, MissedOrderNotice.order_date == order_date)
        .first()
    )
    if exists:
        return
    db.add(MissedOrderNotice(branch_id=branch.id, order_date=order_date))
    db.flush()  # IntegrityError here if another pass recorded it first — handled by the caller
    write_audit_log(  # commits the notice and this row together
        db,
        user_id=None,
        role="SYSTEM",
        action="ORDER_AUTO_SUBMIT_NOTHING",
        entity_type="branch",
        entity_id=branch.id,
        description=(
            f"'{branch.branch_name}' submitted nothing by the cutoff on {order_date.isoformat()} — "
            f"No Previous Order Found (no eligible order on the same weekday in the last {max_weeks} "
            "weeks). No order was submitted."
        ),
    )


def list_unreviewed(db: Session) -> list[Order]:
    return (
        db.query(Order)
        .filter(Order.auto_submitted.is_(True), Order.auto_reviewed_at.is_(None))
        .order_by(Order.delivery_date.desc(), Order.branch_id)
        .all()
    )


def list_open_notices(db: Session) -> list[MissedOrderNotice]:
    """Undismissed "no order" notices whose branch still has no submitted order for that date."""
    has_order = (
        db.query(Order.id)
        .filter(
            Order.branch_id == MissedOrderNotice.branch_id,
            Order.order_date == MissedOrderNotice.order_date,
            Order.status != "DRAFT",
        )
        .exists()
    )
    return (
        db.query(MissedOrderNotice)
        .filter(MissedOrderNotice.reviewed_at.is_(None), ~has_order)
        .order_by(MissedOrderNotice.order_date.desc(), MissedOrderNotice.branch_id)
        .all()
    )


def mark_reviewed(
    db: Session,
    admin: User,
    delivery_date: date | None = None,
    order_id: int | None = None,
    notice_id: int | None = None,
) -> int:
    """Admin acknowledges auto-submitted order(s) and/or dismisses "no order" notices — one order
    (order_id), one notice (notice_id), everything for a delivery date, or everything."""
    stamp = datetime.now(BUSINESS_TZ)
    count = 0
    if notice_id is None:
        query = db.query(Order).filter(Order.auto_submitted.is_(True), Order.auto_reviewed_at.is_(None))
        if order_id is not None:
            query = query.filter(Order.id == order_id)
        if delivery_date is not None:
            query = query.filter(Order.delivery_date == delivery_date)
        for o in query.all():
            o.auto_reviewed_at = stamp
            o.auto_reviewed_by = admin.id
            count += 1
    if order_id is None:
        query = db.query(MissedOrderNotice).filter(MissedOrderNotice.reviewed_at.is_(None))
        if notice_id is not None:
            query = query.filter(MissedOrderNotice.id == notice_id)
        if delivery_date is not None:
            query = query.filter(MissedOrderNotice.order_date == delivery_date - timedelta(days=2))
        for n in query.all():
            n.reviewed_at = stamp
            n.reviewed_by = admin.id
            count += 1
    db.commit()
    return count


# --------------------------------------------------------------------------
# Background scheduler
# --------------------------------------------------------------------------

_stop = threading.Event()
_thread: threading.Thread | None = None


def _run_forever() -> None:
    from app.core.database import SessionLocal

    while not _stop.is_set():
        db = SessionLocal()
        try:
            orders = auto_submit_missed_orders(db)
            if orders:
                logger.info("Auto-submitted %d missed branch order(s).", len(orders))
        except Exception:
            logger.exception("Auto-submit of missed branch orders failed; will retry.")
            db.rollback()
        finally:
            db.close()
        _stop.wait(settings.AUTO_SUBMIT_CHECK_SECONDS)


def start_scheduler() -> None:
    global _thread
    if not settings.AUTO_SUBMIT_MISSED_ORDERS or (_thread and _thread.is_alive()):
        return
    _stop.clear()
    _thread = threading.Thread(target=_run_forever, name="auto-submit-orders", daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    _stop.set()
