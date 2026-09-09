"""
Admin's direct supplier-order builder.

Distinct from assignment_service (which splits one product's total demand
across suppliers without branch detail): here Admin picks a supplier and,
for one or more branches, decides exactly what to send that supplier —
e.g. Malabe: Avocado 200kg, Pineapple 100kg; Kalubovila: Avocado 300kg,
Pineapple 200kg — and both Admin and the Supplier can see that same
branch-level breakdown afterwards.

Saving replaces the full set of lines for a (supplier, delivery_date) pair
— send the complete list each time, not a diff — matching the same
convention used by assignment_service.set_assignments.
"""
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError, NotFoundError, PermissionDeniedError
from app.models.branch import Branch
from app.models.pricing import SupplierPrice
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.supplier import Supplier
from app.models.supplier_order import SupplierOrderItem
from app.models.user import User
from app.schemas.supplier_order import (
    SetSupplierOrderRequest,
    SupplierOrderItemOut,
    SupplierOrderAdminOut,
    SupplierOrderSummaryOut,
    BranchOrderGroup,
    MySupplierOrdersOut,
)


def list_suppliers(db: Session) -> list[Supplier]:
    return db.query(Supplier).filter(Supplier.status == "ACTIVE").order_by(Supplier.supplier_name).all()


def list_supplier_order_dates(db: Session) -> list[date]:
    """Every distinct delivery date any supplier order exists for, most
    recent first — powers the Supplier-wise side of Admin Order History,
    the same way order_service.list_order_dates powers the Branch-wise
    side."""
    rows = (
        db.query(SupplierOrderItem.delivery_date)
        .distinct()
        .order_by(SupplierOrderItem.delivery_date.desc())
        .all()
    )
    return [r[0] for r in rows]


def list_supplier_order_summaries(db: Session, delivery_date: date) -> list[SupplierOrderSummaryOut]:
    """One row per supplier with any order on this delivery date. Reuses
    get_supplier_order per supplier so the total shown here can never
    drift from what expanding that same supplier's row shows — one price
    resolution rule, not two parallel calculations of it."""
    supplier_ids = {
        row[0]
        for row in db.query(SupplierOrderItem.supplier_id)
        .filter(SupplierOrderItem.delivery_date == delivery_date)
        .distinct()
        .all()
    }
    summaries = []
    for supplier_id in supplier_ids:
        order = get_supplier_order(db, supplier_id, delivery_date)
        total_value = sum(it.line_total for it in order.items if it.line_total is not None)
        summaries.append(
            SupplierOrderSummaryOut(
                supplier_id=order.supplier_id,
                supplier_name=order.supplier_name,
                delivery_date=delivery_date,
                line_count=len(order.items),
                total_value=round(total_value, 2),
            )
        )
    summaries.sort(key=lambda s: s.supplier_name)
    return summaries


def get_assigned_quantities(
    db: Session, delivery_date: date, exclude_supplier_id: int | None = None
) -> dict[int, float]:
    """
    Total quantity already handed to suppliers for one delivery date,
    grouped by product — across ALL suppliers except `exclude_supplier_id`
    (normally the supplier Admin is currently editing, so their own
    already-saved lines don't count as "already used up" while deciding
    how much more to give them). Powers the "how much is actually still
    needed" figure on the Supplier Order Builder, so the same demand
    doesn't silently get double-ordered across two different suppliers.
    """
    query = db.query(
        SupplierOrderItem.product_id, func.sum(SupplierOrderItem.quantity)
    ).filter(SupplierOrderItem.delivery_date == delivery_date)
    if exclude_supplier_id is not None:
        query = query.filter(SupplierOrderItem.supplier_id != exclude_supplier_id)
    rows = query.group_by(SupplierOrderItem.product_id).all()
    return {product_id: float(total) for product_id, total in rows}


def get_assigned_quantities_by_branch(
    db: Session, delivery_date: date, exclude_supplier_id: int | None = None
) -> dict[str, float]:
    """
    Same idea as get_assigned_quantities, broken down per branch instead
    of summed across all of them — powers each individual branch column
    on the Order Builder grid, so a branch whose demand has already been
    fully given to another supplier shows 0 remaining for THAT branch
    specifically, rather than the grid inviting Admin to re-enter its
    full original order quantity on top of what's already covered.

    Keyed as "{product_id}:{branch_id}" — the same cell-key convention
    the frontend grid already uses, so it's a direct lookup with no
    reshaping needed on that side.
    """
    query = db.query(
        SupplierOrderItem.product_id,
        SupplierOrderItem.branch_id,
        func.sum(SupplierOrderItem.quantity),
    ).filter(SupplierOrderItem.delivery_date == delivery_date)
    if exclude_supplier_id is not None:
        query = query.filter(SupplierOrderItem.supplier_id != exclude_supplier_id)
    rows = query.group_by(SupplierOrderItem.product_id, SupplierOrderItem.branch_id).all()
    return {f"{product_id}:{branch_id}": float(total) for product_id, branch_id, total in rows}


def get_supplier_price_preview(db: Session, supplier_id: int, delivery_date: date) -> dict[int, "_ResolvedPrice"]:
    """
    Every product this supplier has ANY known price for (submitted or
    Admin-adjusted, any date) — powers a live "Supplier Price" reference
    column on the Order Builder so Admin can see what this supplier
    charges while still deciding quantities, before any order line is
    saved. Uses the exact same resolution rule as a saved line's
    effective_price (see _resolve_prices below), just run across the
    supplier's whole catalogue instead of one specific set of products.
    """
    product_ids = {
        pid
        for (pid,) in db.query(SupplierPrice.product_id)
        .filter(SupplierPrice.supplier_id == supplier_id)
        .distinct()
        .all()
    }
    return _resolve_prices(db, supplier_id, delivery_date, product_ids)


class _ResolvedPrice:
    __slots__ = ("price", "is_estimated", "as_of")

    def __init__(self, price: float, is_estimated: bool, as_of: date):
        self.price = price
        self.is_estimated = is_estimated
        self.as_of = as_of


def _price_from_row(r: SupplierPrice) -> float:
    if r.adjusted_price is not None and r.sent_to_supplier_at is not None:
        return float(r.adjusted_price)
    return float(r.price)


def _resolve_prices(
    db: Session, supplier_id: int, delivery_date: date, product_ids: set[int]
) -> dict[int, "_ResolvedPrice"]:
    """
    Effective price per product_id for one supplier + delivery date, from
    Submit Prices: Admin's sent Adjusted Price if there is one, otherwise
    the supplier's own submitted price. This is the fallback used when an
    order line has no explicit per-line agreed_price of its own.

    Branch orders and supplier pricing both target delivery_date =
    submission_date + 2, so an order's delivery_date usually DOES have an
    exact price match by the time Admin builds the supplier order. It
    won't when a supplier hasn't submitted for that date yet (missed
    cutoff, new product, etc.) — in that case, fall back to that
    supplier's most recent submitted price for the product, on ANY date,
    and flag it as an estimate — better than showing nothing, but the
    caller must be able to tell the difference from a confirmed
    same-date price.
    """
    if not product_ids:
        return {}

    exact_rows = (
        db.query(SupplierPrice)
        .filter(
            SupplierPrice.supplier_id == supplier_id,
            SupplierPrice.delivery_date == delivery_date,
            SupplierPrice.product_id.in_(product_ids),
        )
        .all()
    )
    out: dict[int, _ResolvedPrice] = {}
    for r in exact_rows:
        out[r.product_id] = _ResolvedPrice(_price_from_row(r), is_estimated=False, as_of=r.delivery_date)

    missing = product_ids - set(out.keys())
    if missing:
        fallback_rows = (
            db.query(SupplierPrice)
            .filter(SupplierPrice.supplier_id == supplier_id, SupplierPrice.product_id.in_(missing))
            .order_by(SupplierPrice.product_id, SupplierPrice.delivery_date.desc(), SupplierPrice.id.desc())
            .all()
        )
        seen: set[int] = set()
        for r in fallback_rows:
            if r.product_id in seen:
                continue
            seen.add(r.product_id)
            out[r.product_id] = _ResolvedPrice(_price_from_row(r), is_estimated=True, as_of=r.delivery_date)

    return out


def _to_item_out(
    row: SupplierOrderItem,
    branch: Branch | None,
    product: Product | None,
    category_name: str = "—",
    resolved_prices: dict[int, "_ResolvedPrice"] | None = None,
) -> SupplierOrderItemOut:
    agreed_price = float(row.agreed_price) if row.agreed_price is not None else None
    resolved = (resolved_prices or {}).get(row.product_id)
    if agreed_price is not None:
        effective_price = agreed_price
        price_is_estimated = False
        price_as_of = row.delivery_date
    elif resolved is not None:
        effective_price = resolved.price
        price_is_estimated = resolved.is_estimated
        price_as_of = resolved.as_of
    else:
        effective_price = None
        price_is_estimated = False
        price_as_of = None
    return SupplierOrderItemOut(
        id=row.id,
        branch_id=row.branch_id,
        branch_name=branch.branch_name if branch else "—",
        product_id=row.product_id,
        product_code=product.product_code if product else "—",
        product_description=product.description if product else "—",
        category_name=category_name,
        quantity=float(row.quantity),
        unit_code=row.unit_code,
        agreed_price=agreed_price,
        effective_price=effective_price,
        price_is_estimated=price_is_estimated,
        price_as_of=price_as_of,
        notes=row.notes,
        line_total=round(float(row.quantity) * effective_price, 2) if effective_price is not None else None,
    )


def get_supplier_order(db: Session, supplier_id: int, delivery_date: date) -> SupplierOrderAdminOut:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise NotFoundError("Supplier not found.")

    rows = (
        db.query(SupplierOrderItem)
        .filter(SupplierOrderItem.supplier_id == supplier_id, SupplierOrderItem.delivery_date == delivery_date)
        .all()
    )
    branch_ids = {r.branch_id for r in rows}
    product_ids = {r.product_id for r in rows}
    branches = {b.id: b for b in db.query(Branch).filter(Branch.id.in_(branch_ids)).all()}
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    resolved_prices = _resolve_prices(db, supplier_id, delivery_date, product_ids)

    items = [
        _to_item_out(
            r,
            branches.get(r.branch_id),
            products.get(r.product_id),
            categories.get(products[r.product_id].category_id, "—") if r.product_id in products else "—",
            resolved_prices,
        )
        for r in rows
    ]
    items.sort(key=lambda it: (it.branch_name, it.product_description))

    return SupplierOrderAdminOut(
        supplier_id=supplier.id,
        supplier_name=supplier.supplier_name,
        delivery_date=delivery_date,
        items=items,
    )


def set_supplier_order(
    db: Session,
    admin_user: User,
    supplier_id: int,
    delivery_date: date,
    payload: SetSupplierOrderRequest,
) -> SupplierOrderAdminOut:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise NotFoundError("Supplier not found.")

    branch_ids = {it.branch_id for it in payload.items}
    product_ids = {it.product_id for it in payload.items}

    branches = {b.id: b for b in db.query(Branch).filter(Branch.id.in_(branch_ids)).all()}
    missing_branches = branch_ids - set(branches.keys())
    if missing_branches:
        raise ValidationFailedError(f"Unknown branch id(s): {sorted(missing_branches)}")

    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
    missing_products = product_ids - set(products.keys())
    if missing_products:
        raise ValidationFailedError(f"Unknown product id(s): {sorted(missing_products)}")

    units = {u.id: u.code for u in db.query(ProductUnit).all()}

    existing = {
        (r.branch_id, r.product_id): r
        for r in db.query(SupplierOrderItem)
        .filter(SupplierOrderItem.supplier_id == supplier_id, SupplierOrderItem.delivery_date == delivery_date)
        .all()
    }

    keep_keys = {(it.branch_id, it.product_id) for it in payload.items}
    for key, row in existing.items():
        if key not in keep_keys:
            db.delete(row)

    for entry in payload.items:
        key = (entry.branch_id, entry.product_id)
        product = products[entry.product_id]
        if key in existing:
            row = existing[key]
            row.quantity = entry.quantity
            row.agreed_price = entry.agreed_price
            row.notes = entry.notes
            row.unit_code = units.get(product.unit_id, "?")
        else:
            db.add(
                SupplierOrderItem(
                    supplier_id=supplier_id,
                    branch_id=entry.branch_id,
                    product_id=entry.product_id,
                    delivery_date=delivery_date,
                    quantity=entry.quantity,
                    unit_code=units.get(product.unit_id, "?"),
                    agreed_price=entry.agreed_price,
                    notes=entry.notes,
                    created_by=admin_user.id,
                )
            )

    db.commit()

    write_audit_log(
        db,
        user_id=admin_user.id,
        role="ADMIN",
        action="SUPPLIER_ORDER_SET",
        entity_type="supplier_order",
        entity_id=supplier_id,
        description=(
            f"{len(payload.items)} line(s) set for {supplier.supplier_name}, "
            f"delivery {delivery_date.isoformat()}, across {len(branch_ids)} branch(es)."
        ),
    )

    return get_supplier_order(db, supplier_id, delivery_date)


def get_my_orders_by_branch(
    db: Session, supplier_user: User, delivery_date: date | None = None
) -> MySupplierOrdersOut:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts have orders.")

    available_dates = sorted(
        {
            row[0]
            for row in db.query(SupplierOrderItem.delivery_date)
            .filter(SupplierOrderItem.supplier_id == supplier_user.supplier_id)
            .distinct()
            .all()
        },
        reverse=True,
    )

    if delivery_date is None:
        delivery_date = available_dates[0] if available_dates else None

    if delivery_date is None:
        return MySupplierOrdersOut(delivery_date=None, branches=[], grand_total=0.0, available_delivery_dates=[])

    rows = (
        db.query(SupplierOrderItem)
        .filter(
            SupplierOrderItem.supplier_id == supplier_user.supplier_id,
            SupplierOrderItem.delivery_date == delivery_date,
        )
        .all()
    )
    branch_ids = {r.branch_id for r in rows}
    product_ids = {r.product_id for r in rows}
    branches = {b.id: b for b in db.query(Branch).filter(Branch.id.in_(branch_ids)).all()}
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    resolved_prices = _resolve_prices(db, supplier_user.supplier_id, delivery_date, product_ids)

    by_branch: dict[int, list[SupplierOrderItemOut]] = {}
    for r in rows:
        category_name = categories.get(products[r.product_id].category_id, "—") if r.product_id in products else "—"
        item = _to_item_out(r, branches.get(r.branch_id), products.get(r.product_id), category_name, resolved_prices)
        by_branch.setdefault(r.branch_id, []).append(item)

    groups: list[BranchOrderGroup] = []
    grand_total = 0.0
    for branch_id, items in by_branch.items():
        items.sort(key=lambda it: it.product_description)
        branch_total = sum(it.line_total for it in items if it.line_total is not None)
        grand_total += branch_total
        groups.append(
            BranchOrderGroup(
                branch_id=branch_id,
                branch_name=branches[branch_id].branch_name if branch_id in branches else "—",
                items=items,
                branch_total=round(branch_total, 2),
            )
        )
    groups.sort(key=lambda g: g.branch_name)

    return MySupplierOrdersOut(
        delivery_date=delivery_date,
        branches=groups,
        grand_total=round(grand_total, 2),
        available_delivery_dates=available_dates,
    )
