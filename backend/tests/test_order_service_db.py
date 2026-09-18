"""
DB-backed tests for order_service — the branch order-placement flow.
Covers H-4's "Orders" category: draft create/save/edit, submit, duplicate
submission, submission after deadline, empty order, invalid/negative/
oversized quantity.
"""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.core.errors import ValidationFailedError, PermissionDeniedError, NotFoundError
from app.models.order import OrderLine
from app.models.system import SystemSetting
from app.schemas.order import OrderCreate, OrderLineCreate
from app.services import order_service


def _lines(db_session, order):
    # Order/OrderLine deliberately have no ORM relationship in this
    # codebase (explicit fetch-by-FK everywhere) — mirrors that here.
    return db_session.query(OrderLine).filter(OrderLine.order_id == order.id).all()


def _open_window(db_session, admin_user):
    """Deadline far in the future -> ordering is open for the rest of today."""
    db_session.add(SystemSetting(key="branch_order_deadline", value="23:59", updated_by=admin_user.id))
    db_session.commit()


def _close_window(db_session, admin_user):
    """Deadline effectively at midnight -> ordering is closed for the rest of today."""
    db_session.add(SystemSetting(key="branch_order_deadline", value="00:00", updated_by=admin_user.id))
    db_session.commit()


@pytest.fixture()
def admin_user(make_user):
    return make_user(role="ADMIN")


@pytest.fixture()
def branch_ctx(make_branch, make_user, make_product, db_session, admin_user):
    _open_window(db_session, admin_user)
    branch = make_branch()
    branch_user = make_user(role="BRANCH", branch=branch)
    product = make_product()
    return branch_user, product


def test_save_draft_order_creates_row(db_session, branch_ctx):
    branch_user, product = branch_ctx
    payload = OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=5)])
    order = order_service.save_draft_order(db_session, branch_user, payload)
    assert order.status == "DRAFT"
    lines = _lines(db_session, order)
    assert len(lines) == 1
    assert float(lines[0].quantity) == 5.0


def test_save_draft_order_edit_replaces_lines_not_duplicates(db_session, branch_ctx):
    branch_user, product = branch_ctx
    order_service.save_draft_order(db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=5)]))
    order2 = order_service.save_draft_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=9)])
    )
    # Same order row (one per branch per order_date), lines replaced not appended.
    lines = _lines(db_session, order2)
    assert len(lines) == 1
    assert float(lines[0].quantity) == 9.0


def test_create_order_submits_and_locks_it(db_session, branch_ctx):
    branch_user, product = branch_ctx
    order = order_service.create_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=3)])
    )
    assert order.status == "SUBMITTED"


def test_duplicate_submission_rejected(db_session, branch_ctx):
    branch_user, product = branch_ctx
    order_service.create_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=3)])
    )
    with pytest.raises(ValidationFailedError):
        order_service.create_order(
            db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=3)])
        )


def test_draft_then_submit_converts_in_place_not_a_second_order(db_session, branch_ctx):
    branch_user, product = branch_ctx
    draft = order_service.save_draft_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=3)])
    )
    submitted = order_service.create_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=3)])
    )
    assert submitted.id == draft.id
    assert submitted.status == "SUBMITTED"


def test_submission_after_deadline_rejected(db_session, make_branch, make_user, make_product, admin_user):
    branch = make_branch()
    branch_user = make_user(role="BRANCH", branch=branch)
    product = make_product()
    _close_window(db_session, admin_user)
    with pytest.raises(ValidationFailedError):
        order_service.create_order(
            db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=1)])
        )


def test_empty_order_rejected_at_schema_level(branch_ctx):
    with pytest.raises(ValidationError):
        OrderCreate(lines=[])


def test_negative_quantity_rejected_at_schema_level():
    with pytest.raises(ValidationError):
        OrderLineCreate(product_id=1, quantity=-5)


def test_zero_quantity_rejected_at_schema_level():
    with pytest.raises(ValidationError):
        OrderLineCreate(product_id=1, quantity=0)


def test_oversized_quantity_rejected_at_schema_level():
    # BUG-001 boundary, re-verified here as a permanent regression guard.
    with pytest.raises(ValidationError):
        OrderLineCreate(product_id=1, quantity=999999999)


def test_quantity_at_max_boundary_accepted(db_session, branch_ctx):
    branch_user, product = branch_ctx
    line = OrderLineCreate(product_id=product.id, quantity=99999999.99)
    order = order_service.save_draft_order(db_session, branch_user, OrderCreate(lines=[line]))
    lines = _lines(db_session, order)
    assert float(lines[0].quantity) == 99999999.99


def test_unknown_product_id_rejected(db_session, branch_ctx):
    branch_user, _product = branch_ctx
    with pytest.raises(ValidationFailedError):
        order_service.save_draft_order(
            db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=999999, quantity=1)])
        )


def test_non_branch_account_cannot_place_order(db_session, make_user, make_supplier, make_product, admin_user):
    supplier = make_supplier()
    supplier_user = make_user(role="SUPPLIER", supplier=supplier)
    product = make_product()
    _open_window(db_session, admin_user)
    with pytest.raises(PermissionDeniedError):
        order_service.save_draft_order(
            db_session, supplier_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=1)])
        )


def test_delivery_date_is_order_date_plus_two_days(db_session, branch_ctx):
    branch_user, product = branch_ctx
    order = order_service.save_draft_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=1)])
    )
    assert order.delivery_date == order.order_date + timedelta(days=2)


def test_admin_add_order_line_creates_order_when_branch_has_none(db_session, admin_user, make_branch, make_product):
    branch = make_branch()
    product = make_product()
    delivery_date = date.today() + timedelta(days=2)

    order = order_service.admin_add_order_line(db_session, admin_user, branch.id, product.id, delivery_date, 7)

    assert order.status == "SUBMITTED"
    assert order.delivery_date == delivery_date
    lines = _lines(db_session, order)
    assert len(lines) == 1
    assert float(lines[0].quantity) == 7.0
    assert lines[0].added_by_admin is True


def test_admin_add_order_line_appends_without_touching_branch_lines(db_session, branch_ctx, admin_user, make_product):
    branch_user, product = branch_ctx
    order = order_service.create_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=10)])
    )
    other_product = make_product()

    updated = order_service.admin_add_order_line(
        db_session, admin_user, order.branch_id, other_product.id, order.delivery_date, 4
    )

    assert updated.id == order.id
    lines = {ln.product_id: ln for ln in _lines(db_session, updated)}
    assert len(lines) == 2
    assert float(lines[product.id].quantity) == 10.0
    assert lines[product.id].added_by_admin is False
    assert float(lines[other_product.id].quantity) == 4.0
    assert lines[other_product.id].added_by_admin is True


def test_admin_add_order_line_updates_existing_admin_line(db_session, branch_ctx, admin_user):
    branch_user, product = branch_ctx
    order = order_service.create_order(
        db_session, branch_user, OrderCreate(lines=[OrderLineCreate(product_id=product.id, quantity=10)])
    )
    order_service.admin_add_order_line(db_session, admin_user, order.branch_id, product.id, order.delivery_date, 15)

    lines = _lines(db_session, order)
    assert len(lines) == 1
    assert float(lines[0].quantity) == 15.0


def test_admin_add_order_line_unknown_branch_rejected(db_session, admin_user, make_product):
    product = make_product()
    with pytest.raises(NotFoundError):
        order_service.admin_add_order_line(db_session, admin_user, 999999, product.id, date.today(), 1)
