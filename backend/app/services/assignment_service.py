"""
Admin's supplier assignment step.

For a given product and delivery date, Admin sees every supplier's quoted
price (from supplier_prices) alongside the total quantity branches ordered
that day, and decides how much of that quantity goes to which supplier(s)
at what agreed price — which may differ from the supplier's original quote
if Admin negotiated it. A product's demand can be split across several
suppliers.

Once every product line on a branch's order is fully covered by
assignments, that order's status moves from SUBMITTED to ASSIGNED. If an
assignment is later reduced or removed and a line becomes only partially
covered again, the order status reverts to SUBMITTED — status always
reflects current assignment coverage, not a one-way transition.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError, NotFoundError
from app.models.order import Order, OrderLine
from app.models.pricing import SupplierPrice
from app.models.assignment import SupplierAssignment
from app.models.product import Product, ProductUnit
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.assignment import (
    ProductComparisonOut,
    SupplierQuote,
    AssignmentEntry,
    SetAssignmentsRequest,
)

TOLERANCE = 0.01  # rounding slack when comparing decimal quantities


def _total_demand(db: Session, product_id: int, delivery_date: date) -> float:
    lines = (
        db.query(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .filter(Order.delivery_date == delivery_date, OrderLine.product_id == product_id)
        .all()
    )
    return float(sum(float(ln.quantity) for ln in lines))


def get_product_comparison(db: Session, product_id: int, delivery_date: date) -> ProductComparisonOut:
    product = db.get(Product, product_id)
    if not product:
        raise NotFoundError("Product not found.")
    unit = db.get(ProductUnit, product.unit_id)
    unit_code = unit.code if unit else "—"

    total_demand = _total_demand(db, product_id, delivery_date)

    price_rows = (
        db.query(SupplierPrice)
        .filter(SupplierPrice.product_id == product_id, SupplierPrice.delivery_date == delivery_date)
        .all()
    )
    suppliers = {s.id: s for s in db.query(Supplier).filter(
        Supplier.id.in_([p.supplier_id for p in price_rows])
    ).all()} if price_rows else {}
    quotes = [
        SupplierQuote(
            supplier_id=pr.supplier_id,
            supplier_code=suppliers[pr.supplier_id].supplier_code if pr.supplier_id in suppliers else "—",
            supplier_name=suppliers[pr.supplier_id].supplier_name if pr.supplier_id in suppliers else "—",
            price=float(pr.price),
            unit_code=pr.unit_code,
        )
        for pr in price_rows
    ]
    quotes.sort(key=lambda q: q.price)

    assignment_rows = (
        db.query(SupplierAssignment)
        .filter(
            SupplierAssignment.product_id == product_id,
            SupplierAssignment.delivery_date == delivery_date,
        )
        .all()
    )
    assignments = [
        AssignmentEntry(supplier_id=a.supplier_id, quantity=float(a.quantity), agreed_price=float(a.agreed_price))
        for a in assignment_rows
    ]
    assigned_quantity = sum(a.quantity for a in assignments)

    return ProductComparisonOut(
        product_id=product.id,
        product_code=product.product_code,
        description=product.description,
        unit_code=unit_code,
        delivery_date=delivery_date,
        total_demand=total_demand,
        quotes=quotes,
        assignments=assignments,
        assigned_quantity=assigned_quantity,
        fully_assigned=total_demand > 0 and assigned_quantity >= total_demand - TOLERANCE,
    )


def set_assignments(
    db: Session,
    admin_user: User,
    product_id: int,
    delivery_date: date,
    payload: SetAssignmentsRequest,
) -> ProductComparisonOut:
    product = db.get(Product, product_id)
    if not product:
        raise NotFoundError("Product not found.")

    total_demand = _total_demand(db, product_id, delivery_date)
    requested_total = sum(a.quantity for a in payload.assignments)
    if requested_total > total_demand + TOLERANCE:
        raise ValidationFailedError(
            f"Assigned quantity ({requested_total:g}) exceeds total demand ({total_demand:g}) "
            f"for this product on {delivery_date.isoformat()}."
        )

    supplier_ids = [a.supplier_id for a in payload.assignments]
    suppliers = {s.id for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}
    missing = set(supplier_ids) - suppliers
    if missing:
        raise ValidationFailedError(f"Unknown supplier id(s): {sorted(missing)}")

    existing = {
        a.supplier_id: a
        for a in db.query(SupplierAssignment)
        .filter(
            SupplierAssignment.product_id == product_id,
            SupplierAssignment.delivery_date == delivery_date,
        )
        .all()
    }
    keep_ids = {a.supplier_id for a in payload.assignments}
    for supplier_id, row in existing.items():
        if supplier_id not in keep_ids:
            db.delete(row)

    for entry in payload.assignments:
        if entry.supplier_id in existing:
            row = existing[entry.supplier_id]
            row.quantity = entry.quantity
            row.agreed_price = entry.agreed_price
            row.assigned_by = admin_user.id
        else:
            db.add(
                SupplierAssignment(
                    product_id=product_id,
                    delivery_date=delivery_date,
                    supplier_id=entry.supplier_id,
                    quantity=entry.quantity,
                    agreed_price=entry.agreed_price,
                    assigned_by=admin_user.id,
                )
            )

    db.commit()

    _recompute_order_statuses_for_date(db, delivery_date)
    db.commit()

    write_audit_log(
        db,
        user_id=admin_user.id,
        role="ADMIN",
        action="SUPPLIERS_ASSIGNED",
        entity_type="product_assignment",
        entity_id=product_id,
        description=(
            f"{len(payload.assignments)} supplier(s) assigned for delivery {delivery_date.isoformat()}, "
            f"{requested_total:g} of {total_demand:g} {product.description}."
        ),
    )

    return get_product_comparison(db, product_id, delivery_date)


def _recompute_order_statuses_for_date(db: Session, delivery_date: date) -> None:
    """
    Recomputes SUBMITTED <-> ASSIGNED for every order on this delivery
    date, based on current assignment coverage. Re-derives status from
    scratch each time rather than incrementally patching it, so it can
    never drift out of sync with the underlying assignment rows.
    """
    orders = db.query(Order).filter(Order.delivery_date == delivery_date).all()
    if not orders:
        return

    product_ids = {
        ln.product_id
        for ln in db.query(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .filter(Order.delivery_date == delivery_date)
        .all()
    }
    demand_by_product = {pid: _total_demand(db, pid, delivery_date) for pid in product_ids}
    assigned_by_product: dict[int, float] = {}
    for pid in product_ids:
        rows = (
            db.query(SupplierAssignment)
            .filter(SupplierAssignment.product_id == pid, SupplierAssignment.delivery_date == delivery_date)
            .all()
        )
        assigned_by_product[pid] = sum(float(r.quantity) for r in rows)

    for order in orders:
        if order.status == "CONFIRMED":
            # Delivery already confirmed by the branch — a later change to
            # supplier assignments shouldn't silently reopen a completed
            # order back to SUBMITTED/ASSIGNED.
            continue
        lines = db.query(OrderLine).filter(OrderLine.order_id == order.id).all()
        if not lines:
            continue
        fully_covered = all(
            assigned_by_product.get(ln.product_id, 0.0) >= demand_by_product.get(ln.product_id, 0.0) - TOLERANCE
            for ln in lines
        )
        order.status = "ASSIGNED" if fully_covered else "SUBMITTED"


def get_my_assignments(db: Session, supplier_user: User, delivery_date: date | None = None):
    """
    A supplier's own confirmed assignments: what Admin has assigned to
    them, for which product, at what agreed price — the actual order
    they're expected to fulfill, as opposed to /pricing/mine which shows
    prices they *quoted* (not all of which get assigned).
    """
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts have assignments.")

    available_dates = sorted(
        {
            row[0]
            for row in db.query(SupplierAssignment.delivery_date)
            .filter(SupplierAssignment.supplier_id == supplier_user.supplier_id)
            .distinct()
            .all()
        },
        reverse=True,
    )

    if delivery_date is None:
        delivery_date = available_dates[0] if available_dates else None

    if delivery_date is None:
        return {
            "delivery_date": None,
            "lines": [],
            "grand_total": 0.0,
            "available_delivery_dates": [],
        }

    rows = (
        db.query(SupplierAssignment)
        .filter(
            SupplierAssignment.supplier_id == supplier_user.supplier_id,
            SupplierAssignment.delivery_date == delivery_date,
        )
        .all()
    )
    product_ids = [r.product_id for r in rows]
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}

    lines = []
    grand_total = 0.0
    for r in rows:
        product = products.get(r.product_id)
        line_total = float(r.quantity) * float(r.agreed_price)
        grand_total += line_total
        lines.append(
            {
                "product_id": r.product_id,
                "product_code": product.product_code if product else "—",
                "description": product.description if product else "—",
                "unit_code": units.get(product.unit_id, "—") if product else "—",
                "quantity": float(r.quantity),
                "agreed_price": float(r.agreed_price),
                "line_total": line_total,
            }
        )
    lines.sort(key=lambda ln: ln["description"])

    return {
        "delivery_date": delivery_date,
        "lines": lines,
        "grand_total": grand_total,
        "available_delivery_dates": available_dates,
    }