"""
DB-backed tests for assignment_service._recompute_order_statuses_for_date
— the function refactored for H-3 (N+1 query pattern).

Every scenario below runs a reference/"naive" reimplementation (the exact
per-product, per-order query pattern the function used before this pass)
side by side with the real, now-batched function, on identical data, and
asserts they produce identical order.status results. This is the
old-vs-new equivalence proof the fix requires — not just "the new code
runs without error."

A separate query-count test proves the batching actually reduced query
count as data grows (not just that results still match).
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import event

from app.models.order import Order, OrderLine
from app.models.assignment import SupplierAssignment
from app.services.assignment_service import _recompute_order_statuses_for_date, TOLERANCE

DELIVERY_DATE = date.today() + timedelta(days=2)


def _naive_recompute(db, delivery_date):
    """
    The pre-fix implementation, byte-for-byte in spirit: one query per
    product for demand, one query per product for assigned quantity, one
    query per order for lines. Kept here only as a correctness oracle.
    """
    orders = db.query(Order).filter(Order.delivery_date == delivery_date, Order.status != "DRAFT").all()
    if not orders:
        return {}

    product_ids = {
        ln.product_id
        for ln in db.query(OrderLine)
        .join(Order, Order.id == OrderLine.order_id)
        .filter(Order.delivery_date == delivery_date, Order.status != "DRAFT")
        .all()
    }

    def total_demand(product_id):
        lines = (
            db.query(OrderLine)
            .join(Order, Order.id == OrderLine.order_id)
            .filter(
                Order.delivery_date == delivery_date,
                Order.status != "DRAFT",
                OrderLine.product_id == product_id,
            )
            .all()
        )
        return float(sum(float(ln.quantity) for ln in lines))

    demand_by_product = {pid: total_demand(pid) for pid in product_ids}
    assigned_by_product = {}
    for pid in product_ids:
        rows = (
            db.query(SupplierAssignment)
            .filter(SupplierAssignment.product_id == pid, SupplierAssignment.delivery_date == delivery_date)
            .all()
        )
        assigned_by_product[pid] = sum(float(r.quantity) for r in rows)

    results = {}
    for order in orders:
        if order.status == "CONFIRMED":
            continue
        lines = db.query(OrderLine).filter(OrderLine.order_id == order.id).all()
        if not lines:
            continue
        fully_covered = all(
            assigned_by_product.get(ln.product_id, 0.0) >= demand_by_product.get(ln.product_id, 0.0) - TOLERANCE
            for ln in lines
        )
        results[order.id] = "ASSIGNED" if fully_covered else "SUBMITTED"
    return results


def _make_order(db_session, branch, product, quantity, submitted_by, status="SUBMITTED"):
    order = Order(
        branch_id=branch.id,
        submitted_by=submitted_by.id,
        order_date=DELIVERY_DATE - timedelta(days=2),
        delivery_date=DELIVERY_DATE,
        status=status,
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderLine(order_id=order.id, product_id=product.id, quantity=quantity, unit_code="KG"))
    db_session.commit()
    db_session.refresh(order)
    return order


def _assign(db_session, product, supplier, quantity, agreed_price, assigned_by):
    row = SupplierAssignment(
        product_id=product.id,
        delivery_date=DELIVERY_DATE,
        supplier_id=supplier.id,
        quantity=quantity,
        agreed_price=agreed_price,
        assigned_by=assigned_by.id,
    )
    db_session.add(row)
    db_session.commit()
    return row


@pytest.fixture()
def admin_user(make_user):
    return make_user(role="ADMIN")


def _compare_and_apply(db_session):
    """
    Runs the naive oracle first (read-only, no mutation), then the real
    batched function (which mutates order.status), and asserts they agree
    on every non-CONFIRMED order.
    """
    expected = _naive_recompute(db_session, DELIVERY_DATE)
    _recompute_order_statuses_for_date(db_session, DELIVERY_DATE)
    db_session.commit()
    for order_id, expected_status in expected.items():
        actual = db_session.get(Order, order_id)
        assert actual.status == expected_status, f"order {order_id}: expected {expected_status}, got {actual.status}"


def test_one_product_one_branch_fully_assigned(db_session, make_branch, make_supplier, make_product, admin_user):
    branch = make_branch()
    supplier = make_supplier()
    product = make_product()
    order = _make_order(db_session, branch, product, quantity=10, submitted_by=admin_user)
    _assign(db_session, product, supplier, quantity=10, agreed_price=100, assigned_by=admin_user)

    _compare_and_apply(db_session)
    assert db_session.get(Order, order.id).status == "ASSIGNED"


def test_one_product_partially_assigned(db_session, make_branch, make_supplier, make_product, admin_user):
    branch = make_branch()
    supplier = make_supplier()
    product = make_product()
    order = _make_order(db_session, branch, product, quantity=10, submitted_by=admin_user)
    _assign(db_session, product, supplier, quantity=4, agreed_price=100, assigned_by=admin_user)

    _compare_and_apply(db_session)
    assert db_session.get(Order, order.id).status == "SUBMITTED"


def test_unassigned_order_stays_submitted(db_session, make_branch, make_product, admin_user):
    branch = make_branch()
    product = make_product()
    order = _make_order(db_session, branch, product, quantity=10, submitted_by=admin_user)

    _compare_and_apply(db_session)
    assert db_session.get(Order, order.id).status == "SUBMITTED"


def test_multiple_products_one_branch_mixed_coverage(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    branch = make_branch()
    supplier = make_supplier()
    p1, p2, p3 = make_product(), make_product(), make_product()
    order = _make_order(db_session, branch, p1, quantity=5, submitted_by=admin_user)
    db_session.add(OrderLine(order_id=order.id, product_id=p2.id, quantity=8, unit_code="KG"))
    db_session.add(OrderLine(order_id=order.id, product_id=p3.id, quantity=3, unit_code="KG"))
    db_session.commit()

    # p1 fully covered, p2 fully covered, p3 not assigned at all.
    _assign(db_session, p1, supplier, quantity=5, agreed_price=10, assigned_by=admin_user)
    _assign(db_session, p2, supplier, quantity=8, agreed_price=10, assigned_by=admin_user)

    _compare_and_apply(db_session)
    # Not fully covered (p3 is missing) -> SUBMITTED, not ASSIGNED.
    assert db_session.get(Order, order.id).status == "SUBMITTED"


def test_multiple_branches_same_product_pooled_demand(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    branch_a = make_branch()
    branch_b = make_branch()
    supplier = make_supplier()
    product = make_product()
    order_a = _make_order(db_session, branch_a, product, quantity=6, submitted_by=admin_user)
    order_b = _make_order(db_session, branch_b, product, quantity=4, submitted_by=admin_user)
    # Combined demand is 10; one assignment covers both branches' orders.
    _assign(db_session, product, supplier, quantity=10, agreed_price=50, assigned_by=admin_user)

    _compare_and_apply(db_session)
    assert db_session.get(Order, order_a.id).status == "ASSIGNED"
    assert db_session.get(Order, order_b.id).status == "ASSIGNED"


def test_multiple_suppliers_split_assignment_covers_order(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    branch = make_branch()
    s1, s2 = make_supplier(), make_supplier()
    product = make_product()
    order = _make_order(db_session, branch, product, quantity=10, submitted_by=admin_user)
    _assign(db_session, product, s1, quantity=6, agreed_price=100, assigned_by=admin_user)
    _assign(db_session, product, s2, quantity=4, agreed_price=105, assigned_by=admin_user)

    _compare_and_apply(db_session)
    assert db_session.get(Order, order.id).status == "ASSIGNED"


def test_confirmed_order_is_never_reverted(db_session, make_branch, make_supplier, make_product, admin_user):
    branch = make_branch()
    supplier = make_supplier()
    product = make_product()
    order = _make_order(db_session, branch, product, quantity=10, submitted_by=admin_user, status="CONFIRMED")
    # No assignment at all — if CONFIRMED protection were broken, this
    # would incorrectly flip back to SUBMITTED.
    _compare_and_apply(db_session)
    assert db_session.get(Order, order.id).status == "CONFIRMED"


def test_draft_order_excluded_from_demand_and_never_touched(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    branch = make_branch()
    supplier = make_supplier()
    product = make_product()
    draft = _make_order(db_session, branch, product, quantity=999, submitted_by=admin_user, status="DRAFT")
    real_order = _make_order(db_session, make_branch(), product, quantity=5, submitted_by=admin_user)
    # Assign exactly the real (non-draft) demand — if the draft's 999 were
    # incorrectly counted as demand, this would stay SUBMITTED forever.
    _assign(db_session, product, supplier, quantity=5, agreed_price=20, assigned_by=admin_user)

    _compare_and_apply(db_session)
    assert db_session.get(Order, real_order.id).status == "ASSIGNED"
    assert db_session.get(Order, draft.id).status == "DRAFT"


def test_zero_demand_no_orders_on_date_is_a_noop(db_session):
    # No orders at all for this date -> function must return cleanly.
    _recompute_order_statuses_for_date(db_session, DELIVERY_DATE)
    db_session.commit()  # would raise if anything went wrong


def test_query_count_is_constant_not_linear_in_product_count(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    """
    Proves the fix: query count for _recompute_order_statuses_for_date
    must not grow with the number of distinct products involved. Builds
    two scenarios (3 products, then 12 products) and asserts the second,
    much larger scenario does not issue more queries than the first —
    the old O(N) implementation would have failed this outright.
    """
    supplier = make_supplier()

    def build_scenario(n_products):
        # A fresh branch per scenario — uq_orders_branch_order_date allows
        # only one order per branch per order_date, and both scenarios
        # share the same order_date/delivery_date on purpose (that's what
        # keeps them comparable).
        branch = make_branch()
        order = None
        products = [make_product() for _ in range(n_products)]
        order = Order(
            branch_id=branch.id,
            submitted_by=admin_user.id,
            order_date=DELIVERY_DATE - timedelta(days=2),
            delivery_date=DELIVERY_DATE,
            status="SUBMITTED",
        )
        db_session.add(order)
        db_session.flush()
        for p in products:
            db_session.add(OrderLine(order_id=order.id, product_id=p.id, quantity=1, unit_code="KG"))
        db_session.commit()
        for p in products:
            _assign(db_session, p, supplier, quantity=1, agreed_price=1, assigned_by=admin_user)
        return order

    def count_queries(fn, *args):
        counter = {"n": 0}

        def _on_execute(*a, **kw):
            counter["n"] += 1

        event.listen(db_session.get_bind(), "before_cursor_execute", _on_execute)
        try:
            fn(*args)
        finally:
            event.remove(db_session.get_bind(), "before_cursor_execute", _on_execute)
        return counter["n"]

    small_order = build_scenario(3)
    small_queries = count_queries(_recompute_order_statuses_for_date, db_session, DELIVERY_DATE)
    db_session.commit()

    large_order = build_scenario(12)
    large_queries = count_queries(_recompute_order_statuses_for_date, db_session, DELIVERY_DATE)
    db_session.commit()

    assert db_session.get(Order, small_order.id).status == "ASSIGNED"
    assert db_session.get(Order, large_order.id).status == "ASSIGNED"
    # Constant-ish: the second run covers 4x the products/orders of the
    # first (and re-processes the first order's data too) but must not
    # scale linearly with product count the way the old per-product loop
    # did.
    assert large_queries <= small_queries + 2, (
        f"query count grew with product count ({small_queries} -> {large_queries}); "
        "the N+1 pattern may have regressed"
    )
