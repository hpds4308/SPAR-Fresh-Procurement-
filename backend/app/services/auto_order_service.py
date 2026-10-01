"""
Auto-submission of missed branch orders.

Once the daily branch cutoff (settings.BRANCH_ORDER_DEADLINE) has passed,
any active branch that hasn't submitted today's order gets one submitted
for it, so a forgotten order never means an empty delivery:

- If the branch saved a DRAFT but never pressed Submit, that draft is
  submitted as-is — it's the branch's own, most recent intent, and far
  closer to what they want than a week-old copy.
- Otherwise, the branch's order from the same weekday last week
  (order_date - 7) is copied line for line (ordered quantities; products
  since deactivated are dropped).
- Nothing last week -> the branch's most recent submitted order before
  today is copied instead (same rules).
- No draft and no previous order at all -> nothing to copy, the branch is
  left without an order (same as before this existed).

A branch Admin granted a late-submission exception for today is skipped —
Admin has explicitly given them more time.

Every auto-submitted order is flagged (Order.auto_submitted) and stays
"unreviewed" until Admin acknowledges it, which is what drives the badge
and banner on the Admin dashboard. Runs from a background thread in the
API process (see start_scheduler), once a minute; each run is idempotent
and a no-op before the cutoff or once every branch has an order.
"""
import logging
import threading
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.config import settings
from app.models.branch import Branch
from app.models.order import Order, OrderLine
from app.models.product import Product
from app.models.user import User
from app.services import settings_service
from app.services.order_service import BUSINESS_TZ, _has_deadline_exception, _parse_cutoff

logger = logging.getLogger(__name__)

SOURCE_LAST_WEEK = "LAST_WEEK"
SOURCE_LATEST = "LATEST"
SOURCE_DRAFT = "DRAFT"

# Arbitrary constant key for pg_try_advisory_xact_lock, so two API
# processes (e.g. a redeploy overlapping the old container) never run the
# same pass at once. uq_orders_branch_order_date would still stop a
# duplicate order, but this avoids the noisy IntegrityError path entirely.
_ADVISORY_LOCK_KEY = 725_014_001


def auto_submit_missed_orders(db: Session, now: datetime | None = None) -> list[Order]:
    """One pass: submits today's order for every branch that missed the cutoff. Returns the orders
    it submitted (empty before the cutoff, or when every branch already has one)."""
    now = now.astimezone(BUSINESS_TZ) if now else datetime.now(BUSINESS_TZ)
    cutoff = _parse_cutoff(settings_service.get_setting(db, settings_service.BRANCH_ORDER_DEADLINE))
    if now.time() < cutoff:
        return []

    if db.get_bind().dialect.name == "postgresql":
        got_lock = db.execute(text("SELECT pg_try_advisory_xact_lock(:k)"), {"k": _ADVISORY_LOCK_KEY}).scalar()
        if not got_lock:
            return []

    today = now.date()
    submitted: list[Order] = []
    for branch in db.query(Branch).filter(Branch.status == "ACTIVE").order_by(Branch.id).all():
        existing = db.query(Order).filter(Order.branch_id == branch.id, Order.order_date == today).first()
        if existing and existing.status != "DRAFT":
            continue
        if _has_deadline_exception(db, branch.id, today):
            continue
        order = _submit_from_draft(db, existing) if existing else _submit_from_previous(db, branch, today)
        if order is None:
            continue
        try:
            db.commit()
        except IntegrityError:
            # The branch (or Admin) created today's order between our lookup and commit — theirs wins.
            db.rollback()
            continue
        db.refresh(order)
        submitted.append(order)
        _audit(db, branch, order)
    db.commit()  # releases the advisory lock when nothing was submitted
    return submitted


def _submit_from_draft(db: Session, draft: Order) -> Order | None:
    if not db.query(OrderLine).filter(OrderLine.order_id == draft.id).count():
        return None
    draft.status = "SUBMITTED"
    draft.auto_submitted = True
    draft.auto_submit_source = SOURCE_DRAFT
    return draft


def _active_lines(db: Session, order: Order) -> list[OrderLine]:
    return (
        db.query(OrderLine)
        .join(Product, Product.id == OrderLine.product_id)
        .filter(OrderLine.order_id == order.id, Product.status == "ACTIVE")
        .all()
    )


def _submit_from_previous(db: Session, branch: Branch, today: date) -> Order | None:
    """Copies the same weekday's order from last week, or failing that the branch's most recent
    submitted order before today. An order whose products have all since been deactivated
    doesn't count — the search moves on to the next most recent one."""
    submitted = db.query(Order).filter(Order.branch_id == branch.id, Order.status != "DRAFT")
    source_kind = SOURCE_LAST_WEEK
    source = submitted.filter(Order.order_date == today - timedelta(days=7)).first()
    source_lines = _active_lines(db, source) if source else []
    if not source_lines:
        source_kind = SOURCE_LATEST
        source = None
        for candidate in submitted.filter(Order.order_date < today).order_by(Order.order_date.desc()).limit(30):
            source_lines = _active_lines(db, candidate)
            if source_lines:
                source = candidate
                break
    if not source:
        return None

    # submitted_by is NOT NULL — attribute it to the branch's own account (the order is on their
    # behalf); the auto_submitted flag is what tells everyone the system actually placed it.
    branch_user = (
        db.query(User).filter(User.branch_id == branch.id, User.is_active.is_(True)).order_by(User.id).first()
    )
    order = Order(
        branch_id=branch.id,
        submitted_by=branch_user.id if branch_user else source.submitted_by,
        order_date=today,
        delivery_date=today + timedelta(days=2),
        status="SUBMITTED",
        notes=source.notes,
        auto_submitted=True,
        auto_submit_source=source_kind,
        auto_source_order_id=source.id,
    )
    db.add(order)
    db.flush()
    for ln in source_lines:
        db.add(
            OrderLine(
                order_id=order.id,
                product_id=ln.product_id,
                quantity=ln.quantity,
                unit_code=ln.unit_code,
                notes=ln.notes,
            )
        )
    return order


def _audit(db: Session, branch: Branch, order: Order) -> None:
    line_count = db.query(OrderLine).filter(OrderLine.order_id == order.id).count()
    if order.auto_submit_source == SOURCE_DRAFT:
        how = "the branch's unsent draft"
    else:
        source = db.get(Order, order.auto_source_order_id) if order.auto_source_order_id else None
        which = "last week's order" if order.auto_submit_source == SOURCE_LAST_WEEK else "the latest previous order"
        how = f"{which} ({source.order_date.isoformat()})" if source else which
    write_audit_log(
        db,
        user_id=None,
        role="SYSTEM",
        action="ORDER_AUTO_SUBMITTED",
        entity_type="order",
        entity_id=order.id,
        description=(
            f"'{branch.branch_name}' submitted nothing by the cutoff — auto-submitted {how}, "
            f"{line_count} line(s), delivery {order.delivery_date.isoformat()}."
        ),
    )


def list_unreviewed(db: Session) -> list[Order]:
    return (
        db.query(Order)
        .filter(Order.auto_submitted.is_(True), Order.auto_reviewed_at.is_(None))
        .order_by(Order.delivery_date.desc(), Order.branch_id)
        .all()
    )


def mark_reviewed(db: Session, admin: User, delivery_date: date | None = None, order_id: int | None = None) -> int:
    """Admin acknowledges auto-submitted order(s) — one order, every one for a delivery date, or all."""
    query = db.query(Order).filter(Order.auto_submitted.is_(True), Order.auto_reviewed_at.is_(None))
    if order_id is not None:
        query = query.filter(Order.id == order_id)
    if delivery_date is not None:
        query = query.filter(Order.delivery_date == delivery_date)
    orders = query.all()
    stamp = datetime.now(BUSINESS_TZ)
    for o in orders:
        o.auto_reviewed_at = stamp
        o.auto_reviewed_by = admin.id
    db.commit()
    return len(orders)


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
