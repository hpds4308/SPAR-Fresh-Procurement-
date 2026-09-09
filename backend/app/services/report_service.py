"""
Admin reporting across a date range.

"Spend" throughout this module means committed spend: quantity x agreed
price from supplier_assignments, not raw branch demand — demand has no
price attached until Admin assigns and negotiates it, so it isn't money
yet. Fulfillment is measured by order count (what fraction of branch
orders in range are fully covered by supplier assignments, i.e. status
ASSIGNED or CONFIRMED — CONFIRMED still counts, it's an order that was
assigned *and* delivered), not by summing quantities across products,
since quantities use different units (kg, pcs, ...) and can't be added
together meaningfully.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.models.order import Order, OrderLine
from app.models.assignment import SupplierAssignment
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.supplier import Supplier
from app.schemas.report import (
    AdminReportOut,
    DailyReportRow,
    SupplierSpendRow,
    CategorySpendRow,
    TopProductRow,
    ReportTotals,
)


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
    assignments = (
        db.query(SupplierAssignment)
        .filter(SupplierAssignment.delivery_date >= start_date, SupplierAssignment.delivery_date <= end_date)
        .all()
    )

    products = {
        p.id: p
        for p in db.query(Product)
        .filter(Product.id.in_({a.product_id for a in assignments} | {ln.product_id for ln in lines}))
        .all()
    } if (assignments or lines) else {}
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    suppliers = {
        s.id: s for s in db.query(Supplier).filter(Supplier.id.in_({a.supplier_id for a in assignments})).all()
    } if assignments else {}

    # ---- daily rows ----
    orders_by_date: dict[date, list[Order]] = {}
    for o in orders:
        orders_by_date.setdefault(o.delivery_date, []).append(o)
    assignments_by_date: dict[date, list[SupplierAssignment]] = {}
    for a in assignments:
        assignments_by_date.setdefault(a.delivery_date, []).append(a)

    all_dates = sorted(set(orders_by_date.keys()) | set(assignments_by_date.keys()))
    daily = []
    for d in all_dates:
        day_orders = orders_by_date.get(d, [])
        day_assignments = assignments_by_date.get(d, [])
        daily.append(
            DailyReportRow(
                delivery_date=d,
                orders_count=len(day_orders),
                assigned_orders_count=sum(1 for o in day_orders if o.status in ("ASSIGNED", "CONFIRMED")),
                branches_count=len({o.branch_id for o in day_orders}),
                spend=sum(float(a.quantity) * float(a.agreed_price) for a in day_assignments),
            )
        )

    # ---- by supplier ----
    supplier_agg: dict[int, dict] = {}
    for a in assignments:
        agg = supplier_agg.setdefault(a.supplier_id, {"spend": 0.0, "lines": 0})
        agg["spend"] += float(a.quantity) * float(a.agreed_price)
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
    for a in assignments:
        product = products.get(a.product_id)
        cat_name = categories.get(product.category_id, "—") if product else "—"
        agg = category_agg.setdefault(cat_name, {"spend": 0.0, "lines": 0})
        agg["spend"] += float(a.quantity) * float(a.agreed_price)
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
    for a in assignments:
        product_spend[a.product_id] = product_spend.get(a.product_id, 0.0) + float(a.quantity) * float(
            a.agreed_price
        )

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

    total_spend = sum(float(a.quantity) * float(a.agreed_price) for a in assignments)
    assigned_orders = sum(1 for o in orders if o.status in ("ASSIGNED", "CONFIRMED"))

    return AdminReportOut(
        start_date=start_date,
        end_date=end_date,
        totals=ReportTotals(
            total_orders=len(orders),
            assigned_orders=assigned_orders,
            fulfillment_rate=(assigned_orders / len(orders)) if orders else 0.0,
            total_spend=total_spend,
            days_count=(end_date - start_date).days + 1,
        ),
        daily=daily,
        by_supplier=by_supplier,
        by_category=by_category,
        top_products=top_products,
    )
