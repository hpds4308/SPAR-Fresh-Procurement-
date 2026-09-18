"""
DB-backed tests for supplier_order_service — Admin's direct supplier-order
builder. Covers H-4's "Supplier Orders" category: multiple branches ->
product demand -> supplier assignment -> supplier order, verifying
quantities come out correct.
"""
from datetime import date, timedelta

import pytest

from app.core.errors import ValidationFailedError, NotFoundError
from app.models.order import Order, OrderLine
from app.models.system import SystemSetting
from app.schemas.order import OrderCreate, OrderLineCreate
from app.schemas.supplier_order import SetSupplierOrderRequest, SupplierOrderItemIn
from app.services import order_service, supplier_order_service

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


def test_set_supplier_order_adds_unordered_item_to_branchs_own_order(
    db_session, make_branch, make_user, make_supplier, make_product, admin_user
):
    """
    A Supplier Order line only records what's being sent to a supplier —
    it never touches a branch's own Order/OrderLine. That's surprising in
    practice when the item is one the branch never ordered itself: Admin
    picks a supplier and a quantity for that branch here, expecting the
    branch to see it, but "My Orders" reads from a completely separate
    table. So saving a line for a branch with NO existing line for that
    product must also create one on the branch's real order (added_by_admin),
    while a product the branch already ordered itself is left untouched.
    """
    db_session.add(SystemSetting(key="branch_order_deadline", value="23:59", updated_by=admin_user.id))
    db_session.commit()

    supplier = make_supplier()
    branch = make_branch()
    branch_user = make_user(role="BRANCH", branch=branch)
    ordered_product = make_product()
    unordered_product = make_product()

    own_order = order_service.create_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=ordered_product.id, quantity=12)])
    )

    supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        supplier.id,
        own_order.delivery_date,
        SetSupplierOrderRequest(
            items=[
                SupplierOrderItemIn(branch_id=branch.id, product_id=ordered_product.id, quantity=12, agreed_price=50),
                SupplierOrderItemIn(branch_id=branch.id, product_id=unordered_product.id, quantity=5, agreed_price=None),
            ]
        ),
    )

    lines = {
        ln.product_id: ln
        for ln in db_session.query(OrderLine).filter(OrderLine.order_id == own_order.id).all()
    }
    assert float(lines[ordered_product.id].quantity) == 12.0
    assert lines[ordered_product.id].added_by_admin is False  # the branch's own line, untouched

    assert unordered_product.id in lines  # now visible on the branch's own order
    assert float(lines[unordered_product.id].quantity) == 5.0
    assert lines[unordered_product.id].added_by_admin is True


def test_set_supplier_order_resyncs_a_previously_added_line(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    """Saving again with a different quantity for a line this same sync
    already created (added_by_admin) updates it -- it's still under
    Admin's control until the branch orders it themselves."""
    supplier = make_supplier()
    branch = make_branch()
    product = make_product()

    supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        supplier.id,
        DELIVERY_DATE,
        SetSupplierOrderRequest(
            items=[SupplierOrderItemIn(branch_id=branch.id, product_id=product.id, quantity=5, agreed_price=None)]
        ),
    )
    supplier_order_service.set_supplier_order(
        db_session,
        admin_user,
        supplier.id,
        DELIVERY_DATE,
        SetSupplierOrderRequest(
            items=[SupplierOrderItemIn(branch_id=branch.id, product_id=product.id, quantity=8, agreed_price=None)]
        ),
    )

    line = (
        db_session.query(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .filter(Order.branch_id == branch.id, OrderLine.product_id == product.id)
        .first()
    )
    assert float(line.quantity) == 8.0


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
