"""
Admin reporting across a date range.

"Spend" throughout this module means committed spend: what SPAR has
ordered from suppliers on Supplier Orders (supplier_order_items), at the
same price the Supplier Orders screen and purchase orders show — the
line's own agreed price if Admin set one, else the supplier's effective
price for that delivery date (supplier_order_service._resolve_prices).
Branch demand alone isn't money yet: it only becomes spend once Admin
places it with a supplier.

A branch order counts as fulfilled once every product on it has been
placed with a supplier for that branch and delivery date. Fulfillment is
measured by order count, not by summing quantities across products, since
quantities use different units (kg, pcs, ...) and can't be added together
meaningfully.

(Before Supplier Orders this read supplier_assignments, the old
per-product split — Admin no longer uses that screen, so it's ignored.)
"""
from datetime import date

from sqlalchemy.orm import Session

from app.models.order import Order, OrderLine
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.supplier import Supplier
from app.models.supplier_order import SupplierOrderItem
from app.schemas.report import (
    AdminReportOut,
    DailyReportRow,
    SupplierSpendRow,
    CategorySpendRow,
    TopProductRow,
    ReportTotals,
)
from app.services import supplier_order_service


def _line_spend(db: Session, items: list[SupplierOrderItem]) -> dict[int, float | None]:
    """quantity x effective price per supplier_order_items id; None when no price is known at all."""
    groups: dict[tuple[int, date], list[SupplierOrderItem]] = {}
    for it in items:
        groups.setdefault((it.supplier_id, it.delivery_date), []).append(it)
    out: dict[int, float | None] = {}
    for (supplier_id, delivery_date), rows in groups.items():
        unpriced = {r.product_id for r in rows if r.agreed_price is None}
        resolved = supplier_order_service._resolve_prices(db, supplier_id, delivery_date, unpriced)
        for r in rows:
            if r.agreed_price is not None:
                price = float(r.agreed_price)
            elif r.product_id in resolved:
                price = resolved[r.product_id].price
            else:
                out[r.id] = None
                continue
            out[r.id] = float(r.quantity) * price
    return out


def build_report(db: Session, start_date: date, end_date: date) -> AdminReportOut:
    # DRAFT orders are excluded — they're still the branch's own unsent
    # work, not something Admin has actually received yet.
    orders = (
        db.query(Order)
        .filter(
            Order.delivery_date >= start_date,
            Order.delivery_date <= end_date,
            Order.status != "DRAFT",
        )
        .all()
    )
    order_ids = [o.id for o in orders]
    lines = (
        db.query(OrderLine).filter(OrderLine.order_id.in_(order_ids)).all() if order_ids else []
    )
    items = (
        db.query(SupplierOrderItem)
        .filter(
            SupplierOrderItem.delivery_date >= start_date,
            SupplierOrderItem.delivery_date <= end_date,
            SupplierOrderItem.quantity > 0,
        )
        .all()
    )
    spend = _line_spend(db, items)

    products = {
        p.id: p
        for p in db.query(Product)
        .filter(Product.id.in_({it.product_id for it in items} | {ln.product_id for ln in lines}))
        .all()
    } if (items or lines) else {}
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    suppliers = {
        s.id: s for s in db.query(Supplier).filter(Supplier.id.in_({it.supplier_id for it in items})).all()
    } if items else {}

    # ---- fulfilled orders: every product on the order placed with a supplier ----
    placed = {(it.branch_id, it.product_id, it.delivery_date) for it in items}
    lines_by_order: dict[int, list[OrderLine]] = {}
    for ln in lines:
        if float(ln.quantity) > 0:
            lines_by_order.setdefault(ln.order_id, []).append(ln)
    fulfilled_ids = {
        o.id
        for o in orders
        if lines_by_order.get(o.id)
        and all((o.branch_id, ln.product_id, o.delivery_date) in placed for ln in lines_by_order[o.id])
    }

    # ---- daily rows ----
    orders_by_date: dict[date, list[Order]] = {}
    for o in orders:
        orders_by_date.setdefault(o.delivery_date, []).append(o)
    items_by_date: dict[date, list[SupplierOrderItem]] = {}
    for it in items:
        items_by_date.setdefault(it.delivery_date, []).append(it)

    all_dates = sorted(set(orders_by_date.keys()) | set(items_by_date.keys()))
    daily = []
    for d in all_dates:
        day_orders = orders_by_date.get(d, [])
        daily.append(
            DailyReportRow(
                delivery_date=d,
                orders_count=len(day_orders),
                assigned_orders_count=sum(1 for o in day_orders if o.id in fulfilled_ids),
                branches_count=len({o.branch_id for o in day_orders}),
                spend=sum(spend[it.id] or 0.0 for it in items_by_date.get(d, [])),
            )
        )

    # ---- by supplier ----
    supplier_agg: dict[int, dict] = {}
    for it in items:
        agg = supplier_agg.setdefault(it.supplier_id, {"spend": 0.0, "lines": 0})
        agg["spend"] += spend[it.id] or 0.0
        agg["lines"] += 1
    by_supplier = [
        SupplierSpendRow(
            supplier_id=sid,
            supplier_code=suppliers[sid].supplier_code if sid in suppliers else "—",
            supplier_name=suppliers[sid].supplier_name if sid in suppliers else "—",
            spend=agg["spend"],
            lines_count=agg["lines"],
        )
        for sid, agg in supplier_agg.items()
    ]
    by_supplier.sort(key=lambda r: r.spend, reverse=True)

    # ---- by category ----
    category_agg: dict[str, dict] = {}
    for it in items:
        product = products.get(it.product_id)
        cat_name = categories.get(product.category_id, "—") if product else "—"
        agg = category_agg.setdefault(cat_name, {"spend": 0.0, "lines": 0})
        agg["spend"] += spend[it.id] or 0.0
        agg["lines"] += 1
    by_category = [
        CategorySpendRow(category_name=name, spend=agg["spend"], lines_count=agg["lines"])
        for name, agg in category_agg.items()
    ]
    by_category.sort(key=lambda r: r.spend, reverse=True)

    # ---- top products (by ordered quantity, safe to sum: one product = one unit) ----
    product_agg: dict[int, dict] = {}
    for ln in lines:
        agg = product_agg.setdefault(ln.product_id, {"quantity": 0.0, "orders": set()})
        agg["quantity"] += float(ln.quantity)
        agg["orders"].add(ln.order_id)
    product_spend: dict[int, float] = {}
    for it in items:
        product_spend[it.product_id] = product_spend.get(it.product_id, 0.0) + (spend[it.id] or 0.0)

    top_products = []
    for pid, agg in product_agg.items():
        product = products.get(pid)
        if not product:
            continue
        top_products.append(
            TopProductRow(
                product_id=pid,
                product_code=product.product_code,
                description=product.description,
                category_name=categories.get(product.category_id, "—"),
                unit_code=units.get(product.unit_id, "—"),
                total_quantity=agg["quantity"],
                total_spend=product_spend.get(pid, 0.0),
                order_count=len(agg["orders"]),
            )
        )
    top_products.sort(key=lambda r: r.total_quantity, reverse=True)
    top_products = top_products[:15]

    return AdminReportOut(
        start_date=start_date,
        end_date=end_date,
        totals=ReportTotals(
            total_orders=len(orders),
            assigned_orders=len(fulfilled_ids),
            fulfillment_rate=(len(fulfilled_ids) / len(orders)) if orders else 0.0,
            total_spend=sum(v or 0.0 for v in spend.values()),
            unpriced_lines=sum(1 for v in spend.values() if v is None),
            days_count=(end_date - start_date).days + 1,
        ),
        daily=daily,
        by_supplier=by_supplier,
        by_category=by_category,
        top_products=top_products,
    )
