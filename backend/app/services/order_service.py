"""
Order placement for branches.

Business rule (as agreed with the client): a branch orders once per day,
for delivery *two days later* (delivery date = order date + 2), and must
submit before the daily cutoff (default 14:00, Asia/Colombo) — this
mirrors supplier pricing's own two-day lead time (pricing_service.py), so
a branch's order and the supplier prices used to fulfill it are both
submitted on the same day for the same future delivery date. Branches
never pick a supplier — Admin assigns supplier(s) per line in a later
phase.

All "what time / what date is it" logic lives here, in one place, using
Asia/Colombo as the business timezone regardless of server locale — never
scattered across routes or the frontend, so the rule can't drift.
"""
import io
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo

import openpyxl
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError, PermissionDeniedError, NotFoundError
from app.models.order import Order, OrderLine
from app.models.order_deadline_exception import OrderDeadlineException
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.branch import Branch
from app.models.user import User
from app.schemas._limits import MAX_NUMERIC_10_2
from app.schemas.order import (
    OrderCreate,
    OrderWindowOut,
    DeliveryConfirmRequest,
    ExcelOrderLinePreview,
    ExcelOrderPreviewOut,
    OrderDeadlineExceptionOut,
)
from app.services import settings_service

BUSINESS_TZ = ZoneInfo("Asia/Colombo")


def _parse_cutoff(cutoff_str: str) -> time:
    hh, mm = cutoff_str.split(":")
    return time(hour=int(hh), minute=int(mm))


def get_order_window(db: Session, now: datetime | None = None, branch_id: int | None = None) -> OrderWindowOut:
    """
    Returns whether ordering is currently open, and which delivery date an
    order placed right now would be for. Delivery date is always two
    calendar days after the order date ("Order Date") in business time,
    regardless of cutoff status — the cutoff only gates *whether* a
    submission is accepted, not which date it targets.

    Pass branch_id to also honor a one-off late-submission exception Admin
    may have granted that specific branch for today (see
    grant_late_submission) — omitted entirely for Admin/Supplier callers,
    who have no branch and never need one.
    """
    now = now.astimezone(BUSINESS_TZ) if now else datetime.now(BUSINESS_TZ)
    cutoff_str = settings_service.get_setting(db, settings_service.BRANCH_ORDER_DEADLINE)
    is_open = now.time() < _parse_cutoff(cutoff_str)
    if not is_open and branch_id is not None and _has_deadline_exception(db, branch_id, now.date()):
        is_open = True
    delivery_date = now.date() + timedelta(days=2)
    return OrderWindowOut(
        is_open=is_open,
        delivery_date=delivery_date,
        cutoff_time=cutoff_str,
        server_time=now.isoformat(),
    )


def _has_deadline_exception(db: Session, branch_id: int, order_date: date) -> bool:
    return (
        db.query(OrderDeadlineException)
        .filter(
            OrderDeadlineException.branch_id == branch_id,
            OrderDeadlineException.order_date == order_date,
        )
        .first()
        is not None
    )


def grant_late_submission(db: Session, admin: User, branch_id: int, order_date: date) -> None:
    """
    Lets one branch submit (or keep editing) its order_date order past
    today's normal cutoff — a one-time, per-branch, per-date exception,
    not a change to the cutoff itself. Idempotent: granting twice for the
    same branch/date is a no-op, not a duplicate row.
    """
    branch = db.get(Branch, branch_id)
    if not branch:
        raise NotFoundError("Branch not found.")
    existing = (
        db.query(OrderDeadlineException)
        .filter(OrderDeadlineException.branch_id == branch_id, OrderDeadlineException.order_date == order_date)
        .first()
    )
    if existing:
        return
    db.add(OrderDeadlineException(branch_id=branch_id, order_date=order_date, granted_by=admin.id))
    db.commit()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="ORDER_DEADLINE_EXCEPTION_GRANTED",
        entity_type="branch",
        entity_id=branch_id,
        description=f"Late order submission allowed for '{branch.branch_name}' on {order_date.isoformat()}.",
    )


def revoke_late_submission(db: Session, admin: User, branch_id: int, order_date: date) -> None:
    """Withdraws a previously-granted exception. Safe to call even if none exists."""
    row = (
        db.query(OrderDeadlineException)
        .filter(OrderDeadlineException.branch_id == branch_id, OrderDeadlineException.order_date == order_date)
        .first()
    )
    if not row:
        return
    branch = db.get(Branch, branch_id)
    db.delete(row)
    db.commit()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="ORDER_DEADLINE_EXCEPTION_REVOKED",
        entity_type="branch",
        entity_id=branch_id,
        description=f"Late order submission withdrawn for '{branch.branch_name if branch else branch_id}' on {order_date.isoformat()}.",
    )


def list_deadline_exceptions(db: Session, order_date: date) -> list[OrderDeadlineExceptionOut]:
    """Every branch currently granted a late-submission exception for one order_date."""
    rows = db.query(OrderDeadlineException).filter(OrderDeadlineException.order_date == order_date).all()
    if not rows:
        return []
    branches = {b.id: b for b in db.query(Branch).filter(Branch.id.in_([r.branch_id for r in rows])).all()}
    grantors = {u.id: u for u in db.query(User).filter(User.id.in_([r.granted_by for r in rows])).all()}
    out = [
        OrderDeadlineExceptionOut(
            branch_id=r.branch_id,
            branch_name=branches[r.branch_id].branch_name if r.branch_id in branches else "—",
            order_date=r.order_date,
            granted_by_username=grantors[r.granted_by].username if r.granted_by in grantors else "—",
            created_at=r.created_at,
        )
        for r in rows
    ]
    out.sort(key=lambda e: e.branch_name)
    return out


def _validate_lines(db: Session, payload: OrderCreate) -> tuple[dict[int, Product], dict[int, str]]:
    product_ids = [line.product_id for line in payload.lines]
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
    missing = set(product_ids) - set(products.keys())
    if missing:
        raise ValidationFailedError(f"Unknown product id(s): {sorted(missing)}")
    for pid in product_ids:
        if products[pid].status != "ACTIVE":
            raise ValidationFailedError(f"Product '{products[pid].description}' is not currently orderable.")
    if len(product_ids) != len(set(product_ids)):
        raise ValidationFailedError("Each product can only appear once per order — combine duplicate lines.")
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    return products, units


def _replace_lines(db: Session, order: Order, payload: OrderCreate, products: dict, units: dict) -> None:
    db.query(OrderLine).filter(OrderLine.order_id == order.id).delete()
    for line in payload.lines:
        product = products[line.product_id]
        db.add(
            OrderLine(
                order_id=order.id,
                product_id=product.id,
                quantity=line.quantity,
                unit_code=units.get(product.unit_id, "?"),
                notes=line.notes,
            )
        )


# Header names the order-upload template recognizes, matched
# case/whitespace-insensitively. Product Code is the only real lookup
# key (the one genuinely unique, stable identifier a branch would
# already know); POS Code/Description/Unit are accepted purely so the
# uploader can visually confirm they have the right row — never used to
# override the product's own actual data, the same never-trust-a-
# lower-authority-source rule products.pos_code already follows
# elsewhere in this app.
_EXCEL_COLUMN_ALIASES = {
    "product code": "product_code",
    "pos code": "pos_code",
    "product description": "description",
    "unit": "unit",
    "quantity": "quantity",
}
_EXCEL_REQUIRED_COLUMNS = {"product_code", "quantity"}


def _parse_excel_quantity(raw) -> tuple[float | None, str | None]:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, "Quantity is empty."
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None, f"'{raw}' is not a valid quantity."
    if value <= 0:
        return None, "Quantity must be greater than zero."
    if value > MAX_NUMERIC_10_2:
        return None, f"Quantity exceeds the maximum allowed value ({MAX_NUMERIC_10_2:,.2f})."
    return round(value, 2), None


def parse_order_excel(db: Session, branch_user: User, file_bytes: bytes) -> ExcelOrderPreviewOut:
    """
    Parses an uploaded order Excel into a row-by-row preview — never
    saves anything itself. The branch user reviews this result (rows with
    no `error` prefill quantities on the normal order form) and still has
    to press Save/Submit themselves, going through the exact same
    save_draft_order/create_order path as manual entry — this is purely
    an alternate way to fill in quantities, never a separate way to place
    an order, so cutoff/lock/one-per-day rules are never bypassed.

    A malformed file (wrong format, corrupted, empty) is reported as a
    clean validation error, never left to crash with a raw exception —
    an uploaded file is arbitrary external input and openpyxl's own
    failure modes for "this isn't really a spreadsheet" are varied enough
    that a single broad catch here is the right tool, the same reasoning
    already used for unpredictable external formats in
    harti_import_service.py.
    """
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can upload an order.")

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        header_row = next(rows)
    except Exception:
        raise ValidationFailedError(
            "Could not read this file — make sure it's a valid .xlsx file with a header row."
        )

    header_map: dict[int, str] = {}
    for idx, cell in enumerate(header_row):
        key = _EXCEL_COLUMN_ALIASES.get(str(cell).strip().lower()) if cell is not None else None
        if key:
            header_map[idx] = key

    missing = _EXCEL_REQUIRED_COLUMNS - set(header_map.values())
    if missing:
        raise ValidationFailedError(
            f"Missing required column(s): {', '.join(sorted(missing))}. Expected a header row with: "
            "Product Code, POS Code, Product Description, Unit, Quantity."
        )

    products_by_code = {p.product_code: p for p in db.query(Product).filter(Product.status == "ACTIVE").all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}

    lines: list[ExcelOrderLinePreview] = []
    seen_codes: set[str] = set()
    for row_number, raw_row in enumerate(rows, start=2):  # row 1 is the header
        values = {header_map[i]: raw_row[i] for i in range(len(raw_row)) if i in header_map}
        product_code = str(values.get("product_code") or "").strip()
        if not product_code:
            continue  # a genuinely blank trailing row — common in exported sheets, silently skipped, not an error

        description = str(values["description"]).strip() if values.get("description") is not None else None
        unit_from_file = str(values["unit"]).strip() if values.get("unit") is not None else None

        if product_code in seen_codes:
            lines.append(
                ExcelOrderLinePreview(
                    row_number=row_number,
                    product_code=product_code,
                    description=description,
                    unit_code=unit_from_file,
                    error="Duplicate product code — already appears earlier in this file.",
                )
            )
            continue
        seen_codes.add(product_code)

        product = products_by_code.get(product_code)
        if not product:
            lines.append(
                ExcelOrderLinePreview(
                    row_number=row_number,
                    product_code=product_code,
                    description=description,
                    unit_code=unit_from_file,
                    error="Unknown or inactive product code.",
                )
            )
            continue

        quantity, qty_error = _parse_excel_quantity(values.get("quantity"))
        lines.append(
            ExcelOrderLinePreview(
                row_number=row_number,
                product_code=product_code,
                description=product.description,
                unit_code=units.get(product.unit_id, "—"),
                quantity=quantity,
                product_id=product.id if qty_error is None else None,
                error=qty_error,
            )
        )

    valid_count = sum(1 for ln in lines if ln.error is None)
    return ExcelOrderPreviewOut(lines=lines, valid_line_count=valid_count, error_count=len(lines) - valid_count)


def get_my_order_today(db: Session, branch_user: User) -> Order | None:
    """The branch's own order (DRAFT or beyond) for today's order_date, if any — lets the
    order form resume a draft or show a locked/read-only submitted order after a refresh."""
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts have their own orders.")
    today = datetime.now(BUSINESS_TZ).date()
    return (
        db.query(Order)
        .filter(Order.branch_id == branch_user.branch_id, Order.order_date == today)
        .first()
    )


def get_stock_in_hand_for_branch(db: Session, branch_user: User) -> dict[int, float]:
    """
    Current stock-in-hand per product, for the branch's own location, from
    the POS system — {product_id: quantity}. A product with no entry means
    "unknown," not "zero": it's either not POS-tracked (no pos_code), the
    POS system has no data for it, or the lookup couldn't run at all (POS
    integration not configured, or this branch has no location code set
    yet). All of that is expected and silent — this is a reference figure
    on the order form, never a reason an order can't be placed.
    """
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts have their own orders.")

    branch = db.get(Branch, branch_user.branch_id)
    if not branch or not branch.pos_location_code:
        return {}

    from app.services import pos_stock_service

    products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE", Product.pos_code.isnot(None))
        .all()
    )
    pos_code_to_product_id = {p.pos_code: p.id for p in products}
    if not pos_code_to_product_id:
        return {}

    stock_by_pos_code = pos_stock_service.get_stock_in_hand(
        list(pos_code_to_product_id.keys()), branch.pos_location_code
    )
    return {
        pos_code_to_product_id[code]: quantity
        for code, quantity in stock_by_pos_code.items()
        if code in pos_code_to_product_id
    }


def save_draft_order(db: Session, branch_user: User, payload: OrderCreate) -> Order:
    """
    Saves (creates or updates in place) today's order as a DRAFT — never
    sent to Admin. Calling this again just replaces the draft's lines, it
    never creates a second row (uq_orders_branch_order_date is one row per
    branch per order_date regardless of status, so there's nothing extra
    to enforce here). Rejects if today's order has already moved past
    DRAFT — a draft save is not a way to edit a submitted order.
    """
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can place orders.")

    window = get_order_window(db, branch_id=branch_user.branch_id)
    if not window.is_open:
        raise ValidationFailedError(
            f"Ordering for {window.delivery_date.isoformat()} is closed. "
            f"Daily cutoff is {window.cutoff_time}."
        )

    today = datetime.now(BUSINESS_TZ).date()
    existing = (
        db.query(Order)
        .filter(Order.branch_id == branch_user.branch_id, Order.order_date == today)
        .first()
    )
    if existing and existing.status != "DRAFT":
        raise ValidationFailedError(
            f"Today's order is already {existing.status.lower()} and can no longer be edited here — "
            "contact Admin if it needs to change."
        )

    products, units = _validate_lines(db, payload)

    if existing:
        order = existing
        order.notes = payload.notes
    else:
        order = Order(
            branch_id=branch_user.branch_id,
            submitted_by=branch_user.id,
            order_date=today,
            delivery_date=window.delivery_date,
            status="DRAFT",
            notes=payload.notes,
        )
        db.add(order)
        db.flush()  # get order.id before adding lines

    _replace_lines(db, order, payload, products, units)
    db.commit()
    db.refresh(order)
    return order


def create_order(db: Session, branch_user: User, payload: OrderCreate) -> Order:
    """
    Submits today's order — the "Submit Order" action. If a DRAFT already
    exists for today (see save_draft_order), this converts it in place to
    SUBMITTED with the given lines; otherwise it creates a fresh SUBMITTED
    order directly, so submitting still works for a branch that never
    bothered saving a draft first. Once an order is SUBMITTED (or beyond),
    this rejects further calls — a branch gets exactly one submission per
    order_date (see uq_orders_branch_order_date, the "once a day" key).
    """
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can place orders.")

    window = get_order_window(db, branch_id=branch_user.branch_id)
    if not window.is_open:
        raise ValidationFailedError(
            f"Ordering for {window.delivery_date.isoformat()} is closed. "
            f"Daily cutoff is {window.cutoff_time}."
        )

    today = datetime.now(BUSINESS_TZ).date()
    # One order per branch per order_date — this is the "once a day"
    # business key (see uq_orders_branch_order_date). It intentionally
    # does NOT check delivery_date: delivery_date is now order_date + 2,
    # so two different order_dates never share a delivery_date under the
    # current rule, but this still protects against any legacy rows from
    # before that rule existed that might collide on delivery_date alone.
    existing = (
        db.query(Order)
        .filter(
            Order.branch_id == branch_user.branch_id,
            Order.order_date == today,
        )
        .first()
    )
    if existing and existing.status != "DRAFT":
        raise ValidationFailedError(
            "An order for today has already been submitted. "
            "Contact Admin if it needs to change."
        )

    products, units = _validate_lines(db, payload)

    if existing:
        order = existing
        order.notes = payload.notes
        order.status = "SUBMITTED"
    else:
        order = Order(
            branch_id=branch_user.branch_id,
            submitted_by=branch_user.id,
            order_date=today,
            delivery_date=window.delivery_date,
            status="SUBMITTED",
            notes=payload.notes,
        )
        db.add(order)
        db.flush()  # get order.id before adding lines

    _replace_lines(db, order, payload, products, units)

    try:
        db.commit()
    except IntegrityError:
        # Belt-and-braces: the query above already checks this, but a
        # concurrent double-submit could still race past it, so this
        # catches the database's own constraint instead of surfacing a
        # raw 500 to the branch.
        db.rollback()
        raise ValidationFailedError(
            "An order for today has already been submitted. "
            "Contact Admin if it needs to change."
        )
    db.refresh(order)

    write_audit_log(
        db,
        user_id=branch_user.id,
        role="BRANCH",
        action="ORDER_SUBMITTED",
        entity_type="order",
        entity_id=order.id,
        description=f"Order for delivery {window.delivery_date.isoformat()}, {len(payload.lines)} line(s).",
    )
    return order


def admin_add_order_line(
    db: Session, admin: User, branch_id: int, product_id: int, delivery_date: date, quantity: float
) -> Order:
    """
    Admin adds (or updates) one product/quantity directly onto a branch's
    order for a delivery date — e.g. topping up what the branch itself
    ordered. Only touches that one line, unlike _replace_lines (a full
    per-order overwrite used by the branch's own save/submit).

    Reuses the branch's existing order for that delivery date if there is
    one (promoting a still-open DRAFT to SUBMITTED, since Admin is now
    putting real data on it); otherwise creates a fresh SUBMITTED order.
    """
    branch = db.get(Branch, branch_id)
    if not branch:
        raise NotFoundError("Branch not found.")
    product = db.get(Product, product_id)
    if not product or product.status != "ACTIVE":
        raise ValidationFailedError("Unknown or inactive product.")

    order = (
        db.query(Order)
        .filter(Order.branch_id == branch_id, Order.delivery_date == delivery_date)
        .first()
    )
    if order is None:
        # Same branch/order_date may already have a row (e.g. an
        # in-progress draft) even without a delivery_date match above —
        # reuse it instead of risking uq_orders_branch_order_date.
        order_date = delivery_date - timedelta(days=2)
        order = (
            db.query(Order)
            .filter(Order.branch_id == branch_id, Order.order_date == order_date)
            .first()
        )
    if order is None:
        order = Order(
            branch_id=branch_id,
            submitted_by=admin.id,
            order_date=delivery_date - timedelta(days=2),
            delivery_date=delivery_date,
            status="SUBMITTED",
        )
        db.add(order)
        db.flush()  # get order.id before adding the line
    elif order.status == "DRAFT":
        order.status = "SUBMITTED"

    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    line = (
        db.query(OrderLine)
        .filter(OrderLine.order_id == order.id, OrderLine.product_id == product_id)
        .first()
    )
    if line:
        line.quantity = quantity
        line.added_by_admin = True
    else:
        db.add(
            OrderLine(
                order_id=order.id,
                product_id=product_id,
                quantity=quantity,
                unit_code=units.get(product.unit_id, "?"),
                added_by_admin=True,
            )
        )

    db.commit()
    db.refresh(order)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="ORDER_LINE_ADDED_BY_ADMIN",
        entity_type="order",
        entity_id=order.id,
        description=(
            f"{quantity:g} {units.get(product.unit_id, '?')} of '{product.description}' added for "
            f"'{branch.branch_name}', delivery {delivery_date.isoformat()}."
        ),
    )
    return order


def get_order_detail(db: Session, current_user: User, order_id: int, roles: list[str]) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise NotFoundError("Order not found.")
    is_owner = order.branch_id == current_user.branch_id
    # A DRAFT is never visible to anyone but its own branch — not even
    # Admin — since it hasn't been submitted yet.
    if order.status == "DRAFT" and not is_owner:
        raise NotFoundError("Order not found.")
    if "ADMIN" not in roles and not is_owner:
        raise PermissionDeniedError("You do not have access to this order.")
    return order


def confirm_delivery(db: Session, branch_user: User, order_id: int, payload: DeliveryConfirmRequest) -> Order:
    """
    A branch records what actually arrived for an assigned order. Received
    quantities are free to differ from what was ordered — that's the point,
    it's how shortages, overages, or substitutions get caught and kept on
    record rather than silently assumed to match. Once confirmed, the
    order moves to CONFIRMED and stays there — later assignment changes on
    that delivery date don't reopen it (see assignment_service, which
    skips CONFIRMED orders when recomputing SUBMITTED/ASSIGNED status).
    """
    order = db.get(Order, order_id)
    if not order:
        raise NotFoundError("Order not found.")
    if order.branch_id != branch_user.branch_id:
        raise PermissionDeniedError("You do not have access to this order.")
    if order.status != "ASSIGNED":
        raise ValidationFailedError(
            "Only orders that have been fully assigned to suppliers can be confirmed as delivered. "
            f"This order's status is {order.status}."
        )

    lines = {ln.product_id: ln for ln in db.query(OrderLine).filter(OrderLine.order_id == order.id).all()}
    missing = {entry.product_id for entry in payload.lines} - set(lines.keys())
    if missing:
        raise ValidationFailedError(f"Product id(s) not on this order: {sorted(missing)}")

    for entry in payload.lines:
        line = lines[entry.product_id]
        line.received_quantity = entry.received_quantity
        line.receipt_notes = entry.notes

    order.status = "CONFIRMED"
    order.confirmed_at = datetime.now(BUSINESS_TZ)
    order.confirmed_by = branch_user.id
    db.commit()
    db.refresh(order)

    discrepancies = [
        f"{lines[e.product_id].product_id}: ordered {float(lines[e.product_id].quantity):g}, "
        f"received {e.received_quantity:g}"
        for e in payload.lines
        if abs(e.received_quantity - float(lines[e.product_id].quantity)) > 0.01
    ]
    write_audit_log(
        db,
        user_id=branch_user.id,
        role="BRANCH",
        action="DELIVERY_CONFIRMED",
        entity_type="order",
        entity_id=order.id,
        description=(
            f"Delivery confirmed for {order.delivery_date.isoformat()}."
            + (f" Discrepancies: {'; '.join(discrepancies)}." if discrepancies else " Matched order exactly.")
        ),
    )
    return order


def list_orders(db: Session, current_user: User, roles: list[str], delivery_date: date | None = None) -> list[Order]:
    query = db.query(Order).order_by(Order.created_at.desc())
    if "ADMIN" not in roles:
        query = query.filter(Order.branch_id == current_user.branch_id)
    else:
        # Admin only ever sees orders that have actually been submitted —
        # a DRAFT is still the branch's own private, unsent work.
        query = query.filter(Order.status != "DRAFT")
    if delivery_date:
        query = query.filter(Order.delivery_date == delivery_date)
    return query.all()


def list_order_dates(db: Session) -> list[date]:
    """Every distinct date any SUBMITTED-or-later branch order exists for, most recent
    first — powers the Admin Order History day-by-day browser (which dates have anything
    to show, for Prev/Next navigation and the date picker). Excludes DRAFT orders, which
    aren't visible to Admin at all."""
    rows = (
        db.query(Order.delivery_date)
        .filter(Order.status != "DRAFT")
        .distinct()
        .order_by(Order.delivery_date.desc())
        .all()
    )
    return [r[0] for r in rows]


def get_order_matrix(db: Session, delivery_date: date | None = None):
    """
    Admin view: every active product as a row, every branch as a column,
    quantity ordered by that branch for the given delivery date in each
    cell (blank/omitted if that branch didn't order that product). Shows
    all active products, not just ones with orders, so Admin sees the full
    picture including what nobody ordered.
    """
    available_dates = sorted(
        {row[0] for row in db.query(Order.delivery_date).filter(Order.status != "DRAFT").distinct().all()},
        reverse=True,
    )

    if delivery_date is None:
        delivery_date = available_dates[0] if available_dates else get_order_window(db).delivery_date

    branches = db.query(Branch).filter(Branch.status == "ACTIVE").order_by(Branch.id).all()
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    # Category IDs match the requested display grouping (1=Fruit, 2=Vege
    # Low, 3=Vege Pola, 4=Vege Up); alphabetical within each category.
    products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE")
        .order_by(Product.category_id, Product.description)
        .all()
    )

    lines = (
        db.query(OrderLine, Order.branch_id)
        .join(Order, Order.id == OrderLine.order_id)
        .filter(Order.delivery_date == delivery_date, Order.status != "DRAFT")
        .all()
    )
    # (product_id, branch_id) -> quantity
    qty_map: dict[tuple[int, int], float] = {}
    for line, branch_id in lines:
        qty_map[(line.product_id, branch_id)] = qty_map.get((line.product_id, branch_id), 0.0) + float(
            line.quantity
        )

    rows = []
    for p in products:
        quantities = {}
        for b in branches:
            q = qty_map.get((p.id, b.id))
            if q is not None:
                quantities[str(b.id)] = q
        rows.append(
            {
                "product_id": p.id,
                "product_code": p.product_code,
                "category_name": categories.get(p.category_id, "—"),
                "description": p.description,
                "unit_code": units.get(p.unit_id, "—"),
                "quantities": quantities,
            }
        )

    return {
        "delivery_date": delivery_date,
        "branches": [
            {"branch_id": b.id, "branch_code": b.branch_code, "branch_name": b.branch_name} for b in branches
        ],
        "rows": rows,
        "available_delivery_dates": available_dates,
    }
