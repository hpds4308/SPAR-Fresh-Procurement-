"""
DB-backed tests for the Admin report — report_service.py. Spend and
fulfillment come from Supplier Orders (supplier_order_items).
"""
from datetime import date, timedelta

from app.models.order import Order, OrderLine
from app.models.pricing import SupplierPrice
from app.models.supplier_order import SupplierOrderItem
from app.services import report_service

DELIVERY = date.today() + timedelta(days=2)


def _order(db, branch, user, lines, status="SUBMITTED"):
    order = Order(branch_id=branch.id, submitted_by=user.id, order_date=DELIVERY - timedelta(days=2), delivery_date=DELIVERY, status=status)
    db.add(order)
    db.flush()
    for product, qty in lines:
        db.add(OrderLine(order_id=order.id, product_id=product.id, quantity=qty, unit_code="KG"))
    return order


def _item(db, supplier, branch, product, qty, admin, agreed_price=None):
    db.add(
        SupplierOrderItem(
            supplier_id=supplier.id, branch_id=branch.id, product_id=product.id, delivery_date=DELIVERY,
            quantity=qty, unit_code="KG", agreed_price=agreed_price, created_by=admin.id,
        )
    )


def test_spend_and_fulfillment_come_from_supplier_orders(db_session, make_branch, make_supplier, make_product, make_user):
    admin = make_user(role="ADMIN")
    b1, b2, b3 = make_branch(), make_branch(), make_branch()
    s1, s2 = make_supplier(), make_supplier()
    p1, p2, p3 = make_product(), make_product(), make_product()
    sup_user = make_user(role="SUPPLIER", supplier=s2)
    b1_user, b2_user = make_user(branch=b1), make_user(branch=b2)

    _order(db_session, b1, b1_user, [(p1, 10), (p2, 5)])  # fully placed below
    _order(db_session, b2, b2_user, [(p1, 4), (p3, 2)])  # p3 not placed -> not fulfilled
    _order(db_session, b3, make_user(branch=b3), [(p2, 1)], status="DRAFT")  # ignored

    # Line's own agreed price.
    _item(db_session, s1, b1, p1, 10, admin, agreed_price=50)
    # No agreed price -> supplier's submitted price for the date (30).
    db_session.add(SupplierPrice(supplier_id=s2.id, product_id=p2.id, delivery_date=DELIVERY, price=30, unit_code="KG", submitted_by=sup_user.id))
    _item(db_session, s2, b1, p2, 5, admin)
    _item(db_session, s1, b2, p1, 4, admin, agreed_price=50)
    # No price anywhere -> counted as unpriced, left out of spend.
    _item(db_session, s2, b2, p3, 0, admin)  # zero quantity: ignored entirely
    _item(db_session, s1, b2, p2, 3, admin)
    db_session.commit()

    r = report_service.build_report(db_session, DELIVERY - timedelta(days=1), DELIVERY)

    assert r.totals.total_orders == 2
    assert r.totals.assigned_orders == 1
    assert r.totals.fulfillment_rate == 0.5
    assert r.totals.total_spend == 10 * 50 + 5 * 30 + 4 * 50
    assert r.totals.unpriced_lines == 1
    assert [(d.delivery_date, d.orders_count, d.assigned_orders_count, d.spend) for d in r.daily] == [
        (DELIVERY, 2, 1, 850.0)
    ]
    by_supplier = {s.supplier_id: (s.spend, s.lines_count) for s in r.by_supplier}
    assert by_supplier == {s1.id: (700.0, 3), s2.id: (150.0, 1)}
    assert sum(c.spend for c in r.by_category) == 850.0
    top = {p.product_id: (p.total_quantity, p.total_spend) for p in r.top_products}
    assert top[p1.id] == (14.0, 700.0)
    assert top[p2.id] == (5.0, 150.0)


def test_export_endpoint(client, db_session, make_user, auth_headers):
    admin = make_user(role="ADMIN")
    q = f"?start_date={(DELIVERY - timedelta(days=6)).isoformat()}&end_date={DELIVERY.isoformat()}"
    r = client.get(f"/api/v1/reports/admin/summary{q}", headers=auth_headers(admin))
    assert r.status_code == 200, r.text
    assert "unpriced_lines" in r.json()["totals"]
    x = client.get(f"/api/v1/reports/admin/summary/export{q}", headers=auth_headers(admin))
    assert x.status_code == 200 and x.content[:2] == b"PK"
