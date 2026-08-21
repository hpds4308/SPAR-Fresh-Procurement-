"""
Order placement for branches.

Business rule (as agreed with the client): a branch orders once per day,
for delivery *the same day* (delivery date = order date = today), and
must submit before the daily cutoff (default 14:00, Asia/Colombo).
Branches never pick a supplier — Admin assigns supplier(s) per line in a
later phase.

All "what time / what date is it" logic lives here, in one place, using
Asia/Colombo as the business timezone regardless of server locale — never
scattered across routes or the frontend, so the rule can't drift.
"""
from datetime import datetime, date, timedelta, time
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError, PermissionDeniedError, NotFoundError
from app.models.order import Order, OrderLine
from app.models.product import Product, ProductUnit
from app.models.branch import Branch
from app.models.user import User
from app.schemas.order import OrderCreate, OrderWindowOut, DeliveryConfirmRequest
from app.services import settings_service

BUSINESS_TZ = ZoneInfo("Asia/Colombo")


def _parse_cutoff(cutoff_str: str) -> time:
    hh, mm = cutoff_str.split(":")
    return time(hour=int(hh), minute=int(mm))


def get_order_window(db: Session, now: datetime | None = None) -> OrderWindowOut:
    """
    Returns whether ordering is currently open, and which delivery date an
    order placed right now would be for. Delivery date is always the same
    calendar day as the order date ("Order Date") in business time,
    regardless of cutoff status — the cutoff only gates *whether* a
    submission is accepted, not which date it targets.
    """
    now = now.astimezone(BUSINESS_TZ) if now else datetime.now(BUSINESS_TZ)
    cutoff_str = settings_service.get_setting(db, settings_service.BRANCH_ORDER_DEADLINE)
    is_open = now.time() < _parse_cutoff(cutoff_str)
    delivery_date = now.date()
    return OrderWindowOut(
        is_open=is_open,
        delivery_date=delivery_date,
        cutoff_time=cutoff_str,
        server_time=now.isoformat(),
    )


def create_order(db: Session, branch_user: User, payload: OrderCreate) -> Order:
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can place orders.")

    window = get_order_window(db)
    if not window.is_open:
        raise ValidationFailedError(
            f"Ordering for {window.delivery_date.isoformat()} is closed. "
            f"Daily cutoff is {window.cutoff_time}."
        )

    today = datetime.now(BUSINESS_TZ).date()
    # One order per branch per order_date — this is the true "once a day"
    # business key now that delivery_date always == order_date (see
    # uq_orders_branch_order_date). It intentionally does NOT check
    # delivery_date: a leftover order placed under the old rule (order_date
    # = yesterday, delivery_date = today) must never block a genuinely new
    # order placed today just because they happen to share a delivery_date.
    existing = (
        db.query(Order)
        .filter(
            Order.branch_id == branch_user.branch_id,
            Order.order_date == today,
        )
        .first()
    )
    if existing:
        raise ValidationFailedError(
            "An order for today has already been submitted. "
            "Contact Admin if it needs to change."
        )

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


def cancel_order(db: Session, branch_user: User, order_id: int) -> None:
    """
    Lets a branch undo its own mistake (wrong quantity, wrong product)
    without needing Admin to do it for them — previously there was no way
    to do this at all; create_order's own error message says "contact
    Admin if it needs to change" because that really was the only option.

    Deliberately restricted to SUBMITTED orders, still before today's
    cutoff: SupplierAssignment is keyed by (product, delivery_date,
    supplier) — not by order — so once Admin starts assigning suppliers
    against the aggregated demand for today, a branch's order is no
    longer just that branch's own business to unwind. ASSIGNED/CONFIRMED
    orders still require contacting Admin (now easier via Messages).
    """
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can cancel their own orders.")
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise NotFoundError("Order not found.")
    if order.branch_id != branch_user.branch_id:
        raise PermissionDeniedError("You can only cancel your own branch's orders.")
    if order.status != "SUBMITTED":
        raise ValidationFailedError(
            f"This order is already {order.status} and can no longer be cancelled here — "
            "contact Admin if it needs to change."
        )
    window = get_order_window(db)
    today = datetime.now(BUSINESS_TZ).date()
    if order.order_date != today or not window.is_open:
        raise ValidationFailedError(
            f"Today's ordering cutoff ({window.cutoff_time}) has passed — this order can no longer be cancelled here."
        )

    write_audit_log(
        db,
        user_id=branch_user.id,
        role="BRANCH",
        action="ORDER_CANCELLED",
        entity_type="order",
        entity_id=order.id,
        description=f"Order for delivery {order.delivery_date.isoformat()} cancelled before cutoff.",
    )
    db.delete(order)
    db.commit()


def get_order_detail(db: Session, current_user: User, order_id: int, roles: list[str]) -> Order:
    order = db.get(Order, order_id)
    if not order:
        raise NotFoundError("Order not found.")
    if "ADMIN" not in roles and order.branch_id != current_user.branch_id:
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
    if delivery_date:
        query = query.filter(Order.delivery_date == delivery_date)
    return query.all()


def list_order_dates(db: Session) -> list[date]:
    """Every distinct date any branch order exists for, most recent first — powers the
    Admin Order History day-by-day browser (which dates have anything to show, for
    Prev/Next navigation and the date picker)."""
    rows = db.query(Order.delivery_date).distinct().order_by(Order.delivery_date.desc()).all()
    return [r[0] for r in rows]


def get_order_matrix(db: Session, delivery_date: date | None = None):
    """
    Admin view: every active product as a row, every branch as a column,
    quantity ordered by that branch for the given delivery date in each
    cell (blank/omitted if that branch didn't order that product). Shows
    all active products, not just ones with orders, so Admin sees the full
    picture including what nobody ordered.
    """
    from app.models.branch import Branch
    from app.models.product import Product, ProductCategory, ProductUnit
    from app.models.order import Order, OrderLine

    available_dates = sorted(
        {row[0] for row in db.query(Order.delivery_date).distinct().all()}, reverse=True
    )

    if delivery_date is None:
        delivery_date = available_dates[0] if available_dates else get_order_window(db).delivery_date

    branches = db.query(Branch).filter(Branch.status == "ACTIVE").order_by(Branch.id).all()
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE")
        .order_by(Product.category_id, Product.id)
        .all()
    )

    lines = (
        db.query(OrderLine, Order.branch_id)
        .join(Order, Order.id == OrderLine.order_id)
        .filter(Order.delivery_date == delivery_date)
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
