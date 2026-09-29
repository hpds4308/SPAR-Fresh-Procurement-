"""
DB-backed tests for purchase_order_service — issuing a PO from a
supplier's saved order, its per-branch breakdown, re-issue/outdated
detection, cancellation, and supplier-side access.
"""
from datetime import date, timedelta

import pytest

from app.core.errors import NotFoundError, ValidationFailedError
from app.schemas.supplier_order import SetSupplierOrderRequest, SupplierOrderItemIn
from app.services import purchase_order_service, supplier_order_service

DELIVERY_DATE = date.today() + timedelta(days=2)


@pytest.fixture()
def admin_user(make_user):
    return make_user(role="ADMIN")


def _save_order(db, admin, supplier, items):
    supplier_order_service.set_supplier_order(
        db, admin, supplier.id, DELIVERY_DATE, SetSupplierOrderRequest(items=[SupplierOrderItemIn(**i) for i in items])
    )


def test_issue_builds_supplier_po_and_one_branch_po_per_branch(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    supplier = make_supplier(supplier_code="SUP01")
    b1 = make_branch(branch_code="BR01", branch_name="Alpha")
    b2 = make_branch(branch_code="BR02", branch_name="Beta")
    avocado, pineapple = make_product(description="AVOCADO"), make_product(description="PINEAPPLE")
    _save_order(
        db_session,
        admin_user,
        supplier,
        [
            dict(branch_id=b1.id, product_id=avocado.id, quantity=200, agreed_price=50),
            dict(branch_id=b1.id, product_id=pineapple.id, quantity=100, agreed_price=30),
            dict(branch_id=b2.id, product_id=avocado.id, quantity=300, agreed_price=50),
        ],
    )

    po = purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)
    detail = purchase_order_service.to_detail(db_session, po, include_outdated=True)

    assert detail.po_number == f"PO-{DELIVERY_DATE:%y%m%d}-SUP01"
    assert detail.revision == 1 and detail.status == "ISSUED"
    assert detail.total_amount == 200 * 50 + 100 * 30 + 300 * 50
    assert not detail.is_outdated

    # Supplier PO: avocado combined across both branches.
    consolidated = {ln.product_description: ln for ln in detail.consolidated_lines}
    assert consolidated["AVOCADO"].quantity == 500
    assert consolidated["AVOCADO"].line_total == 25000
    assert consolidated["PINEAPPLE"].quantity == 100

    # Branch POs.
    assert [b.po_number for b in detail.branches] == [f"{detail.po_number}-BR01", f"{detail.po_number}-BR02"]
    assert detail.branches[0].total == 200 * 50 + 100 * 30
    assert [ln.quantity for ln in detail.branches[1].lines] == [300]


def test_same_product_at_different_prices_stays_separate_on_supplier_po(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    supplier = make_supplier()
    b1, b2 = make_branch(), make_branch()
    product = make_product()
    _save_order(
        db_session,
        admin_user,
        supplier,
        [
            dict(branch_id=b1.id, product_id=product.id, quantity=10, agreed_price=50),
            dict(branch_id=b2.id, product_id=product.id, quantity=5, agreed_price=55),
        ],
    )
    po = purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)
    lines = purchase_order_service.to_detail(db_session, po).consolidated_lines
    assert [(ln.quantity, ln.unit_price) for ln in lines] == [(10, 50), (5, 55)]


def test_cannot_issue_without_an_order_or_with_unpriced_lines(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    supplier = make_supplier()
    with pytest.raises(ValidationFailedError, match="no order saved"):
        purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)

    branch, product = make_branch(), make_product(description="MANGO")
    _save_order(db_session, admin_user, supplier, [dict(branch_id=branch.id, product_id=product.id, quantity=10)])
    with pytest.raises(ValidationFailedError, match="MANGO"):
        purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)


def test_editing_order_marks_po_outdated_and_reissue_bumps_revision(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    supplier = make_supplier()
    branch, product = make_branch(), make_product()
    _save_order(db_session, admin_user, supplier, [dict(branch_id=branch.id, product_id=product.id, quantity=10, agreed_price=20)])
    po = purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)
    number = po.po_number

    # Issuing again with nothing changed is a no-op.
    assert purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE).revision == 1

    _save_order(db_session, admin_user, supplier, [dict(branch_id=branch.id, product_id=product.id, quantity=15, agreed_price=20)])
    rows = purchase_order_service.list_admin_rows(db_session, DELIVERY_DATE)
    assert rows[0].is_outdated
    # The issued PO itself is untouched by the edit.
    assert purchase_order_service.to_detail(db_session, po).branches[0].lines[0].quantity == 10

    po = purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)
    assert po.revision == 2 and po.po_number == number
    detail = purchase_order_service.to_detail(db_session, po, include_outdated=True)
    assert detail.branches[0].lines[0].quantity == 15 and not detail.is_outdated


def test_cancel_then_reissue(db_session, make_branch, make_supplier, make_product, admin_user):
    supplier = make_supplier()
    branch, product = make_branch(), make_product()
    _save_order(db_session, admin_user, supplier, [dict(branch_id=branch.id, product_id=product.id, quantity=1, agreed_price=1)])
    po = purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)

    po = purchase_order_service.cancel_purchase_order(db_session, admin_user, po.id)
    assert po.status == "CANCELLED" and po.cancelled_at is not None
    with pytest.raises(ValidationFailedError):
        purchase_order_service.cancel_purchase_order(db_session, admin_user, po.id)

    po = purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)
    assert po.status == "ISSUED" and po.revision == 2 and po.cancelled_at is None


def test_supplier_sees_only_their_own_purchase_orders(
    db_session, make_branch, make_supplier, make_product, make_user, admin_user
):
    mine, other = make_supplier(), make_supplier()
    branch, product = make_branch(), make_product()
    for s in (mine, other):
        _save_order(db_session, admin_user, s, [dict(branch_id=branch.id, product_id=product.id, quantity=1, agreed_price=1)])
    my_po = purchase_order_service.issue_purchase_order(db_session, admin_user, mine.id, DELIVERY_DATE)
    other_po = purchase_order_service.issue_purchase_order(db_session, admin_user, other.id, DELIVERY_DATE)

    supplier_user = make_user(role="SUPPLIER", supplier=mine)
    assert [p.id for p in purchase_order_service.list_my_purchase_orders(db_session, supplier_user)] == [my_po.id]
    assert purchase_order_service.get_my_purchase_order(db_session, supplier_user, my_po.id).id == my_po.id
    with pytest.raises(NotFoundError):
        purchase_order_service.get_my_purchase_order(db_session, supplier_user, other_po.id)


def test_purchase_order_endpoints_are_role_gated(
    client, auth_headers, db_session, make_branch, make_supplier, make_product, make_user, admin_user
):
    supplier = make_supplier()
    branch, product = make_branch(), make_product()
    _save_order(db_session, admin_user, supplier, [dict(branch_id=branch.id, product_id=product.id, quantity=2, agreed_price=5)])

    resp = client.post(
        "/api/v1/purchase-orders/admin",
        json={"supplier_id": supplier.id, "delivery_date": DELIVERY_DATE.isoformat()},
        headers=auth_headers(admin_user),
    )
    assert resp.status_code == 200, resp.text
    po_id = resp.json()["id"]

    supplier_user = make_user(role="SUPPLIER", supplier=supplier)
    assert client.get("/api/v1/purchase-orders/admin/dates", headers=auth_headers(supplier_user)).status_code == 403
    resp = client.get(f"/api/v1/purchase-orders/mine/{po_id}", headers=auth_headers(supplier_user))
    assert resp.status_code == 200
    assert resp.json()["total_amount"] == 10
    branch_user = make_user(role="BRANCH", branch=branch)
    assert client.get("/api/v1/purchase-orders/mine", headers=auth_headers(branch_user)).status_code == 403


def test_branch_sees_only_its_own_branch_po(
    db_session, make_branch, make_supplier, make_product, make_user, admin_user
):
    supplier = make_supplier(supplier_code="SUP09")
    mine = make_branch(branch_code="BR05")
    other = make_branch()
    outside = make_branch()
    product = make_product()
    _save_order(
        db_session,
        admin_user,
        supplier,
        [
            dict(branch_id=mine.id, product_id=product.id, quantity=10, agreed_price=5),
            dict(branch_id=other.id, product_id=product.id, quantity=90, agreed_price=5),
        ],
    )
    po = purchase_order_service.issue_purchase_order(db_session, admin_user, supplier.id, DELIVERY_DATE)

    branch_user = make_user(role="BRANCH", branch=mine)
    [summary] = purchase_order_service.list_branch_purchase_orders(db_session, branch_user)
    assert summary.po_number == f"{po.po_number}-BR05"
    assert summary.total_amount == 50 and summary.branch_count == 1

    detail = purchase_order_service.get_branch_purchase_order(db_session, branch_user, po.id)
    assert [b.branch_id for b in detail.branches] == [mine.id]
    assert [ln.quantity for ln in detail.consolidated_lines] == [10]

    outsider = make_user(role="BRANCH", branch=outside)
    assert purchase_order_service.list_branch_purchase_orders(db_session, outsider) == []
    with pytest.raises(NotFoundError):
        purchase_order_service.get_branch_purchase_order(db_session, outsider, po.id)


def test_branch_can_search_its_purchase_orders_by_number_or_supplier(
    db_session, make_branch, make_supplier, make_product, make_user, admin_user
):
    branch = make_branch(branch_code="BR07")
    product = make_product()
    fresh = make_supplier(supplier_code="SUP11", supplier_name="Fresh Farms")
    green = make_supplier(supplier_code="SUP12", supplier_name="Green Valley")
    for s in (fresh, green):
        _save_order(db_session, admin_user, s, [dict(branch_id=branch.id, product_id=product.id, quantity=1, agreed_price=1)])
        purchase_order_service.issue_purchase_order(db_session, admin_user, s.id, DELIVERY_DATE)
    user = make_user(role="BRANCH", branch=branch)

    def search(q):
        return [p.po_number for p in purchase_order_service.list_branch_purchase_orders(db_session, user, q)]

    number = f"PO-{DELIVERY_DATE:%y%m%d}-SUP11-BR07"
    assert search(number) == [number]
    assert search(number.replace("-", "").lower()) == [number]  # punctuation/case ignored
    assert search("green valley") == [f"PO-{DELIVERY_DATE:%y%m%d}-SUP12-BR07"]
    assert search("SUP99") == []
    assert len(search("")) == 2
