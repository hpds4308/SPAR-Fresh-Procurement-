"""
DB-backed tests for auto_order_service — submitting last week's order (or
the unsent draft) for a branch that missed the daily cutoff.
"""
from datetime import datetime, timedelta

import pytest

from app.core.errors import ValidationFailedError
from app.models.missed_order_notice import MissedOrderNotice
from app.models.order import Order, OrderLine
from app.models.order_deadline_exception import OrderDeadlineException
from app.models.system import SystemSetting
from app.services import auto_order_service, order_service
from app.services.order_service import BUSINESS_TZ

NOW = datetime(2026, 9, 30, 15, 0, tzinfo=BUSINESS_TZ)  # a Wednesday, one hour past a 14:00 cutoff
TODAY = NOW.date()
LAST_WEEK = TODAY - timedelta(days=7)


@pytest.fixture()
def admin_user(db_session, make_user):
    admin = make_user(role="ADMIN")
    db_session.add(SystemSetting(key="branch_order_deadline", value="14:00", updated_by=admin.id))
    db_session.commit()
    return admin


@pytest.fixture()
def branch_ctx(make_branch, make_user, make_product, admin_user):
    branch = make_branch()
    branch_user = make_user(role="BRANCH", branch=branch)
    return branch, branch_user, make_product(), make_product()


def _order(db_session, branch, user, order_date, status, lines):
    order = Order(
        branch_id=branch.id,
        submitted_by=user.id,
        order_date=order_date,
        delivery_date=order_date + timedelta(days=2),
        status=status,
    )
    db_session.add(order)
    db_session.flush()
    for product, qty in lines:
        db_session.add(OrderLine(order_id=order.id, product_id=product.id, quantity=qty, unit_code="KG"))
    db_session.commit()
    return order


def _today_order(db_session, branch):
    return db_session.query(Order).filter(Order.branch_id == branch.id, Order.order_date == TODAY).first()


def _lines(db_session, order):
    return {ln.product_id: float(ln.quantity) for ln in db_session.query(OrderLine).filter(OrderLine.order_id == order.id)}


def test_copies_last_weeks_order_after_cutoff(db_session, branch_ctx):
    branch, user, p1, p2 = branch_ctx
    source = _order(db_session, branch, user, LAST_WEEK, "CONFIRMED", [(p1, 5), (p2, 2.5)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.status == "SUBMITTED"
    assert order.auto_submitted is True
    assert order.auto_submit_source == "LAST_WEEK"
    assert order.auto_source_order_id == source.id
    assert order.delivery_date == TODAY + timedelta(days=2)
    assert order.auto_reviewed_at is None
    assert _lines(db_session, order) == {p1.id: 5.0, p2.id: 2.5}


def test_does_nothing_before_cutoff(db_session, branch_ctx):
    branch, user, p1, _ = branch_ctx
    _order(db_session, branch, user, LAST_WEEK, "SUBMITTED", [(p1, 5)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW.replace(hour=13, minute=59))

    assert _today_order(db_session, branch) is None


def test_leaves_a_submitted_order_alone(db_session, branch_ctx):
    branch, user, p1, p2 = branch_ctx
    _order(db_session, branch, user, LAST_WEEK, "SUBMITTED", [(p1, 5)])
    mine = _order(db_session, branch, user, TODAY, "SUBMITTED", [(p2, 1)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.id == mine.id
    assert order.auto_submitted is False
    assert _lines(db_session, order) == {p2.id: 1.0}


def test_submits_unsent_draft_instead_of_last_week(db_session, branch_ctx):
    branch, user, p1, p2 = branch_ctx
    _order(db_session, branch, user, LAST_WEEK, "SUBMITTED", [(p1, 5)])
    draft = _order(db_session, branch, user, TODAY, "DRAFT", [(p2, 3)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.id == draft.id
    assert order.status == "SUBMITTED"
    assert order.auto_submit_source == "DRAFT"
    assert _lines(db_session, order) == {p2.id: 3.0}


def test_no_order_last_week_copies_latest_previous_order(db_session, branch_ctx):
    branch, user, p1, p2 = branch_ctx
    _order(db_session, branch, user, TODAY - timedelta(days=12), "SUBMITTED", [(p1, 9)])
    latest = _order(db_session, branch, user, TODAY - timedelta(days=2), "SUBMITTED", [(p2, 4)])
    _order(db_session, branch, user, TODAY - timedelta(days=1), "DRAFT", [(p1, 1)])  # never submitted - ignored

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.auto_submit_source == "LATEST"
    assert order.auto_source_order_id == latest.id
    assert _lines(db_session, order) == {p2.id: 4.0}


def _open_notice_branch_ids(db_session):
    return {n.branch_id for n in auto_order_service.list_open_notices(db_session)}


def test_no_previous_order_at_all_leaves_admin_a_notice(db_session, branch_ctx, admin_user):
    branch, _, _, _ = branch_ctx

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    auto_order_service.auto_submit_missed_orders(db_session, now=NOW + timedelta(minutes=1))

    assert _today_order(db_session, branch) is None
    notices = db_session.query(MissedOrderNotice).filter(MissedOrderNotice.branch_id == branch.id).all()
    assert [n.order_date for n in notices] == [TODAY]  # once, not once per run
    assert branch.id in _open_notice_branch_ids(db_session)

    auto_order_service.mark_reviewed(db_session, admin_user, notice_id=notices[0].id)
    assert branch.id not in _open_notice_branch_ids(db_session)


def test_notice_clears_once_the_branch_has_an_order(db_session, branch_ctx, admin_user):
    branch, _, p1, _ = branch_ctx
    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    assert branch.id in _open_notice_branch_ids(db_session)

    order_service.admin_add_order_line(db_session, admin_user, branch.id, p1.id, TODAY + timedelta(days=2), 3)

    assert branch.id not in _open_notice_branch_ids(db_session)


def test_admin_can_remove_lines_from_auto_submitted_order_only(db_session, branch_ctx, admin_user):
    branch, user, p1, p2 = branch_ctx
    _order(db_session, branch, user, LAST_WEEK, "SUBMITTED", [(p1, 5), (p2, 2)])
    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    order = _today_order(db_session, branch)

    order_service.admin_remove_order_line(db_session, admin_user, branch.id, p2.id, order.delivery_date)
    assert _lines(db_session, order) == {p1.id: 5.0}

    # The branch's own submitted order is still protected.
    with pytest.raises(ValidationFailedError):
        order_service.admin_remove_order_line(db_session, admin_user, branch.id, p1.id, LAST_WEEK + timedelta(days=2))


def test_skips_inactive_products_and_branches_with_late_exception(db_session, branch_ctx, make_branch, make_user, admin_user):
    branch, user, p1, p2 = branch_ctx
    p2.status = "INACTIVE"
    db_session.commit()
    _order(db_session, branch, user, LAST_WEEK, "SUBMITTED", [(p1, 5), (p2, 2)])

    late_branch = make_branch()
    late_user = make_user(role="BRANCH", branch=late_branch)
    _order(db_session, late_branch, late_user, LAST_WEEK, "SUBMITTED", [(p1, 1)])
    db_session.add(OrderDeadlineException(branch_id=late_branch.id, order_date=TODAY, granted_by=admin_user.id))
    db_session.commit()

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    assert _lines(db_session, _today_order(db_session, branch)) == {p1.id: 5.0}
    assert _today_order(db_session, late_branch) is None


def test_second_run_is_a_no_op_and_review_clears_flag(db_session, branch_ctx, admin_user):
    branch, user, p1, _ = branch_ctx
    _order(db_session, branch, user, LAST_WEEK, "SUBMITTED", [(p1, 5)])

    first = auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    second = auto_order_service.auto_submit_missed_orders(db_session, now=NOW + timedelta(minutes=1))
    assert [o.branch_id for o in first] == [branch.id]
    assert second == []

    order = _today_order(db_session, branch)
    assert order.id in {o.id for o in auto_order_service.list_unreviewed(db_session)}
    assert auto_order_service.mark_reviewed(db_session, admin_user, delivery_date=order.delivery_date) >= 1
    db_session.refresh(order)
    assert order.auto_reviewed_at is not None
    assert order.auto_reviewed_by == admin_user.id
