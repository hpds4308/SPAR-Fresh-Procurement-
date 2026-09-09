"""
DB-backed tests for supplier_order_service — Admin's direct supplier-order
builder. Covers H-4's "Supplier Orders" category: multiple branches ->
product demand -> supplier assignment -> supplier order, verifying
quantities come out correct.
"""
from datetime import date, timedelta

import pytest

from app.core.errors import ValidationFailedError, NotFoundError
from app.schemas.supplier_order import SetSupplierOrderRequest, SupplierOrderItemIn
from app.services import supplier_order_service

DELIVERY_DATE = date.today() + timedelta(days=2)


@pytest.fixture()
def admin_user(make_user):
    return make_user(role="ADMIN")


def test_set_supplier_order_across_multiple_branches(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    supplier = make_supplier()
    b1, b2 = make_branch(), make_branch()
    p1, p2 = make_product(), make_product()

    result = supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        supplier.id,
        DELIVERY_DATE,
        SetSupplierOrderRequest(
            items=[
                SupplierOrderItemIn(branch_id=b1.id, product_id=p1.id, quantity=200, agreed_price=50),
                SupplierOrderItemIn(branch_id=b1.id, product_id=p2.id, quantity=100, agreed_price=30),
                SupplierOrderItemIn(branch_id=b2.id, product_id=p1.id, quantity=300, agreed_price=50),
            ]
        ),
    )
    assert len(result.items) == 3
    by_branch_product = {(it.branch_id, it.product_id): it.quantity for it in result.items}
    assert by_branch_product[(b1.id, p1.id)] == 200
    assert by_branch_product[(b1.id, p2.id)] == 100
    assert by_branch_product[(b2.id, p1.id)] == 300


def test_set_supplier_order_replaces_full_set_not_a_diff(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    supplier = make_supplier()
    branch = make_branch()
    p1, p2 = make_product(), make_product()

    supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        supplier.id,
        DELIVERY_DATE,
        SetSupplierOrderRequest(
            items=[SupplierOrderItemIn(branch_id=branch.id, product_id=p1.id, quantity=100, agreed_price=10)]
        ),
    )
    # Second save omits p1 entirely and adds p2 -- p1's line must be gone.
    result = supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        supplier.id,
        DELIVERY_DATE,
        SetSupplierOrderRequest(
            items=[SupplierOrderItemIn(branch_id=branch.id, product_id=p2.id, quantity=50, agreed_price=20)]
        ),
    )
    product_ids = {it.product_id for it in result.items}
    assert product_ids == {p2.id}


def test_assigned_quantities_exclude_own_supplier(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    """
    get_assigned_quantities powers "how much is still needed" while
    editing a given supplier's order -- that supplier's own existing
    lines must not count against themselves.
    """
    branch = make_branch()
    product = make_product()
    s1, s2 = make_supplier(), make_supplier()

    supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        s1.id,
        DELIVERY_DATE,
        SetSupplierOrderRequest(
            items=[SupplierOrderItemIn(branch_id=branch.id, product_id=product.id, quantity=100, agreed_price=10)]
        ),
    )

    assigned_excluding_s1 = supplier_order_service.get_assigned_quantities(
        db_session, DELIVERY_DATE, exclude_supplier_id=s1.id
    )
    assert assigned_excluding_s1.get(product.id, 0) == 0

    assigned_including_s1 = supplier_order_service.get_assigned_quantities(db_session, DELIVERY_DATE)
    assert assigned_including_s1[product.id] == 100

    assigned_excluding_s2 = supplier_order_service.get_assigned_quantities(
        db_session, DELIVERY_DATE, exclude_supplier_id=s2.id
    )
    assert assigned_excluding_s2[product.id] == 100  # s1's line still counts when excluding a different supplier


def test_unknown_branch_rejected(db_session, make_supplier, make_product, admin_user):
    supplier = make_supplier()
    product = make_product()
    with pytest.raises(ValidationFailedError):
        supplier_order_service.set_supplier_order(
            db_session,
            admin_user,
            supplier.id,
            DELIVERY_DATE,
            SetSupplierOrderRequest(
                items=[SupplierOrderItemIn(branch_id=999999, product_id=product.id, quantity=10, agreed_price=1)]
            ),
        )


def test_unknown_product_rejected(db_session, make_supplier, make_branch, admin_user):
    supplier = make_supplier()
    branch = make_branch()
    with pytest.raises(ValidationFailedError):
        supplier_order_service.set_supplier_order(
            db_session,
            admin_user,
            supplier.id,
            DELIVERY_DATE,
            SetSupplierOrderRequest(
                items=[SupplierOrderItemIn(branch_id=branch.id, product_id=999999, quantity=10, agreed_price=1)]
            ),
        )


def test_unknown_supplier_rejected(db_session, make_branch, make_product, admin_user):
    branch = make_branch()
    product = make_product()
    with pytest.raises(NotFoundError):
        supplier_order_service.set_supplier_order(
            db_session,
            admin_user,
            999999,
            DELIVERY_DATE,
            SetSupplierOrderRequest(
                items=[SupplierOrderItemIn(branch_id=branch.id, product_id=product.id, quantity=10, agreed_price=1)]
            ),
        )


def test_line_total_uses_quantity_times_effective_price(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    supplier = make_supplier()
    branch = make_branch()
    product = make_product()
    result = supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        supplier.id,
        DELIVERY_DATE,
        SetSupplierOrderRequest(
            items=[SupplierOrderItemIn(branch_id=branch.id, product_id=product.id, quantity=4, agreed_price=25)]
        ),
    )
    assert result.items[0].line_total == 100.0  # 4 * 25
