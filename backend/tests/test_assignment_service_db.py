"""
DB-backed tests for assignment_service — Admin's supplier-assignment step,
consolidation (branch demand -> product total -> supplier allocation),
and second-lowest-price/savings against real assigned rows. Covers H-4's
"Assignment", "Consolidation", and "Lowest/Second Lowest Supplier Price"
categories.
"""
from datetime import date, timedelta

import pytest

from app.core.errors import ValidationFailedError, NotFoundError
from app.models.order import Order, OrderLine
from app.models.pricing import SupplierPrice
from app.schemas.assignment import SetAssignmentsRequest, AssignmentIn
from app.services import assignment_service

DELIVERY_DATE = date.today() + timedelta(days=2)


@pytest.fixture()
def admin_user(make_user):
    return make_user(role="ADMIN")


def _order_with_line(db_session, branch, product, quantity, submitted_by):
    order = Order(
        branch_id=branch.id,
        submitted_by=submitted_by.id,
        order_date=DELIVERY_DATE - timedelta(days=2),
        delivery_date=DELIVERY_DATE,
        status="SUBMITTED",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderLine(order_id=order.id, product_id=product.id, quantity=quantity, unit_code="KG"))
    db_session.commit()
    return order


def _quote(db_session, supplier, product, price, submitted_by):
    row = SupplierPrice(
        supplier_id=supplier.id,
        product_id=product.id,
        delivery_date=DELIVERY_DATE,
        price=price,
        unit_code="KG",
        submitted_by=submitted_by.id,
    )
    db_session.add(row)
    db_session.commit()
    return row


# --- Consolidation: branch demand -> product total ------------------------


def test_consolidation_pools_demand_across_branches(
    db_session, make_branch, make_product, make_user, admin_user
):
    product = make_product()
    b1, b2, b3 = make_branch(), make_branch(), make_branch()
    _order_with_line(db_session, b1, product, 4, admin_user)
    _order_with_line(db_session, b2, product, 6, admin_user)
    _order_with_line(db_session, b3, product, 2.5, admin_user)

    total = assignment_service._total_demand(db_session, product.id, DELIVERY_DATE)
    assert total == 12.5


def test_consolidation_ignores_draft_orders(db_session, make_branch, make_product, admin_user):
    product = make_product()
    branch = make_branch()
    _order_with_line(db_session, branch, product, 10, admin_user)
    draft = Order(
        branch_id=make_branch().id,
        submitted_by=admin_user.id,
        order_date=DELIVERY_DATE - timedelta(days=2),
        delivery_date=DELIVERY_DATE,
        status="DRAFT",
    )
    db_session.add(draft)
    db_session.flush()
    db_session.add(OrderLine(order_id=draft.id, product_id=product.id, quantity=1000, unit_code="KG"))
    db_session.commit()

    total = assignment_service._total_demand(db_session, product.id, DELIVERY_DATE)
    assert total == 10  # the 1000-qty draft must not count


# --- Second-lowest price / savings, against real assigned rows ------------


def test_second_lowest_and_savings_reflect_real_quotes(
    db_session, make_branch, make_supplier, make_product, make_user, admin_user
):
    product = make_product()
    branch = make_branch()
    s1, s2, s3 = make_supplier(), make_supplier(), make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)
    _quote(db_session, s1, product, 300, admin_user)
    _quote(db_session, s2, product, 320, admin_user)
    _quote(db_session, s3, product, 310, admin_user)

    comparison = assignment_service.get_product_comparison(db_session, product.id, DELIVERY_DATE)
    assert comparison.second_lowest_price == 310  # next distinct tier above 300

    assignment_service.set_assignments(
        db_session,
        admin_user,
        product.id,
        DELIVERY_DATE,
        SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=s1.id, quantity=10, agreed_price=300)]),
    )
    updated = assignment_service.get_product_comparison(db_session, product.id, DELIVERY_DATE)
    entry = next(a for a in updated.assignments if a.supplier_id == s1.id)
    # (second_lowest - agreed_price) * quantity = (310 - 300) * 10 = 100
    assert entry.savings == 100.0


def test_tied_lowest_price_second_lowest_skips_to_next_distinct_tier(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    product = make_product()
    branch = make_branch()
    s1, s2, s3 = make_supplier(), make_supplier(), make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)
    _quote(db_session, s1, product, 300, admin_user)
    _quote(db_session, s2, product, 300, admin_user)
    _quote(db_session, s3, product, 320, admin_user)

    comparison = assignment_service.get_product_comparison(db_session, product.id, DELIVERY_DATE)
    assert comparison.second_lowest_price == 320  # not another 300


def test_all_tied_prices_no_second_lowest(db_session, make_branch, make_supplier, make_product, admin_user):
    product = make_product()
    branch = make_branch()
    s1, s2 = make_supplier(), make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)
    _quote(db_session, s1, product, 300, admin_user)
    _quote(db_session, s2, product, 300, admin_user)

    comparison = assignment_service.get_product_comparison(db_session, product.id, DELIVERY_DATE)
    assert comparison.second_lowest_price is None


def test_single_supplier_no_second_lowest_no_savings(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    product = make_product()
    branch = make_branch()
    s1 = make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)
    _quote(db_session, s1, product, 300, admin_user)

    assignment_service.set_assignments(
        db_session,
        admin_user,
        product.id,
        DELIVERY_DATE,
        SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=s1.id, quantity=10, agreed_price=300)]),
    )
    comparison = assignment_service.get_product_comparison(db_session, product.id, DELIVERY_DATE)
    assert comparison.second_lowest_price is None
    assert comparison.assignments[0].savings is None


def test_missing_supplier_price_product_with_no_quotes_at_all(db_session, make_branch, make_product, admin_user):
    product = make_product()
    branch = make_branch()
    _order_with_line(db_session, branch, product, 10, admin_user)

    comparison = assignment_service.get_product_comparison(db_session, product.id, DELIVERY_DATE)
    assert comparison.quotes == []
    assert comparison.second_lowest_price is None


# --- Assignment: single/multi supplier, full/partial, invalid inputs ------


def test_full_assignment_single_supplier(db_session, make_branch, make_supplier, make_product, admin_user):
    product = make_product()
    branch = make_branch()
    supplier = make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)

    result = assignment_service.set_assignments(
        db_session,
        admin_user,
        product.id,
        DELIVERY_DATE,
        SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=supplier.id, quantity=10, agreed_price=100)]),
    )
    assert result.fully_assigned is True
    assert result.assigned_quantity == 10


def test_partial_assignment_multiple_suppliers(
    db_session, make_branch, make_supplier, make_product, admin_user
):
    product = make_product()
    branch = make_branch()
    s1, s2 = make_supplier(), make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)

    result = assignment_service.set_assignments(
        db_session,
        admin_user,
        product.id,
        DELIVERY_DATE,
        SetAssignmentsRequest(
            assignments=[
                AssignmentIn(supplier_id=s1.id, quantity=6, agreed_price=100),
                AssignmentIn(supplier_id=s2.id, quantity=3, agreed_price=105),
            ]
        ),
    )
    assert result.fully_assigned is False
    assert result.assigned_quantity == 9


def test_reassignment_replaces_previous_split(db_session, make_branch, make_supplier, make_product, admin_user):
    product = make_product()
    branch = make_branch()
    s1, s2 = make_supplier(), make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)

    assignment_service.set_assignments(
        db_session,
        admin_user,
        product.id,
        DELIVERY_DATE,
        SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=s1.id, quantity=10, agreed_price=100)]),
    )
    # Reassign entirely to s2 -- s1's row must be removed, not left stale.
    result = assignment_service.set_assignments(
        db_session,
        admin_user,
        product.id,
        DELIVERY_DATE,
        SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=s2.id, quantity=10, agreed_price=90)]),
    )
    supplier_ids = {a.supplier_id for a in result.assignments}
    assert supplier_ids == {s2.id}


def test_assignment_exceeding_demand_rejected(db_session, make_branch, make_supplier, make_product, admin_user):
    product = make_product()
    branch = make_branch()
    supplier = make_supplier()
    _order_with_line(db_session, branch, product, 10, admin_user)

    with pytest.raises(ValidationFailedError):
        assignment_service.set_assignments(
            db_session,
            admin_user,
            product.id,
            DELIVERY_DATE,
            SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=supplier.id, quantity=999, agreed_price=100)]),
        )


def test_assignment_unknown_supplier_rejected(db_session, make_branch, make_product, admin_user):
    product = make_product()
    branch = make_branch()
    _order_with_line(db_session, branch, product, 10, admin_user)

    with pytest.raises(ValidationFailedError):
        assignment_service.set_assignments(
            db_session,
            admin_user,
            product.id,
            DELIVERY_DATE,
            SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=999999, quantity=5, agreed_price=100)]),
        )


def test_assignment_unknown_product_rejected(db_session, make_supplier, admin_user):
    supplier = make_supplier()
    with pytest.raises(NotFoundError):
        assignment_service.set_assignments(
            db_session,
            admin_user,
            999999,
            DELIVERY_DATE,
            SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=supplier.id, quantity=5, agreed_price=100)]),
        )
