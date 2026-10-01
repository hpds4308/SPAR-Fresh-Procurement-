"""
Tests for auto_order_service — what gets submitted for a branch that missed
the daily cutoff: its unsent draft, else its own order from the same
weekday 1, 2, 3 ... weeks back (most recent first), else nothing plus a
"No Previous Order Found" notice for Admin.

"Today" is Thursday 01 Oct 2026, one hour past a 14:00 cutoff, so the
weekly fallback tries Thu 24 Sep, then Thu 17 Sep, then Thu 10 Sep, ...
"""
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.core.errors import ValidationFailedError
from app.models.missed_order_notice import MissedOrderNotice
from app.models.order import Order, OrderLine
from app.models.order_deadline_exception import OrderDeadlineException
from app.models.system import AuditLog, SystemSetting
from app.services import auto_order_service, order_service
from app.services.order_service import BUSINESS_TZ

NOW = datetime(2026, 10, 1, 15, 0, tzinfo=BUSINESS_TZ)  # Thursday, one hour past a 14:00 cutoff
TODAY = NOW.date()
SEP_24 = date(2026, 9, 24)  # Thu, 1 week back (delivered Sat 26 Sep)
SEP_17 = date(2026, 9, 17)  # Thu, 2 weeks back (delivered Sat 19 Sep)
SEP_10 = date(2026, 9, 10)  # Thu, 3 weeks back (delivered Sat 12 Sep)


@pytest.fixture()
def admin_user(db_session, make_user):
    admin = make_user(role="ADMIN")
    db_session.add(SystemSetting(key="branch_order_deadline", value="14:00", updated_by=admin.id))
    db_session.commit()
    return admin


@pytest.fixture()
def papiliyana(make_branch, make_user, make_product, admin_user):
    branch = make_branch(branch_name="Papiliyana")
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


def _orders_on(db_session, branch, order_date):
    return db_session.query(Order).filter(Order.branch_id == branch.id, Order.order_date == order_date).all()


def _today_order(db_session, branch, today=TODAY):
    rows = _orders_on(db_session, branch, today)
    assert len(rows) <= 1
    return rows[0] if rows else None


def _lines(db_session, order):
    return {ln.product_id: float(ln.quantity) for ln in db_session.query(OrderLine).filter(OrderLine.order_id == order.id)}


def _open_notice_branch_ids(db_session):
    return {n.branch_id for n in auto_order_service.list_open_notices(db_session)}


# --------------------------------------------------------------------------
# The weekly fallback (spec tests 1-8)
# --------------------------------------------------------------------------


def test_1_uses_the_order_from_one_week_back(db_session, papiliyana):
    branch, user, p1, p2 = papiliyana
    source = _order(db_session, branch, user, SEP_24, "CONFIRMED", [(p1, 5), (p2, 2.5)])
    _order(db_session, branch, user, SEP_17, "CONFIRMED", [(p1, 99)])  # older — must not win

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.status == "SUBMITTED"
    assert order.auto_submitted is True
    assert order.auto_submit_source == auto_order_service.SOURCE_PREVIOUS_WEEK
    assert order.auto_source_order_id == source.id
    assert auto_order_service.weeks_back(order, source.order_date) == 1
    assert order.auto_reviewed_at is None
    assert _lines(db_session, order) == {p1.id: 5.0, p2.id: 2.5}


def test_2_falls_back_two_weeks_when_last_week_is_missing(db_session, papiliyana):
    branch, user, p1, _ = papiliyana
    source = _order(db_session, branch, user, SEP_17, "SUBMITTED", [(p1, 7)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.auto_source_order_id == source.id
    assert auto_order_service.weeks_back(order, source.order_date) == 2
    assert _lines(db_session, order) == {p1.id: 7.0}


def test_3_falls_back_three_weeks(db_session, papiliyana):
    branch, user, p1, _ = papiliyana
    source = _order(db_session, branch, user, SEP_10, "ASSIGNED", [(p1, 3)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.auto_source_order_id == source.id
    assert auto_order_service.weeks_back(order, source.order_date) == 3


def test_4_no_eligible_history_creates_nothing_and_notifies_admin(db_session, papiliyana):
    branch, _, _, _ = papiliyana

    result = auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    assert result == []
    assert _orders_on(db_session, branch, TODAY) == []  # no empty/invalid order
    assert branch.id in _open_notice_branch_ids(db_session)
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "ORDER_AUTO_SUBMIT_NOTHING", AuditLog.entity_id == branch.id)
        .all()
    )
    assert len(audit) == 1
    assert "No Previous Order Found" in audit[0].description


def test_5_never_uses_another_branchs_order(db_session, papiliyana, make_branch, make_user):
    branch, _, p1, _ = papiliyana
    other = make_branch(branch_name="Other Branch")
    other_user = make_user(role="BRANCH", branch=other)
    _order(db_session, other, other_user, SEP_24, "SUBMITTED", [(p1, 50)])
    _order(db_session, other, other_user, TODAY, "SUBMITTED", [(p1, 50)])  # other branch is done for today

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    assert _orders_on(db_session, branch, TODAY) == []
    assert branch.id in _open_notice_branch_ids(db_session)


def test_6_never_overwrites_or_duplicates_an_already_submitted_order(db_session, papiliyana):
    branch, user, p1, p2 = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 5)])
    mine = _order(db_session, branch, user, TODAY, "SUBMITTED", [(p2, 1)])

    assert auto_order_service.auto_submit_missed_orders(db_session, now=NOW) == []

    rows = _orders_on(db_session, branch, TODAY)
    assert [o.id for o in rows] == [mine.id]
    assert rows[0].auto_submitted is False
    assert _lines(db_session, rows[0]) == {p2.id: 1.0}


def test_7_new_order_gets_the_current_delivery_date_not_the_historical_one(db_session, papiliyana):
    branch, user, p1, _ = papiliyana
    source = _order(db_session, branch, user, SEP_17, "CONFIRMED", [(p1, 5)])
    assert source.delivery_date == date(2026, 9, 19)

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.order_date == TODAY
    assert order.delivery_date == date(2026, 10, 3)
    assert order.delivery_date == order_service.get_order_window(db_session, now=NOW).delivery_date


def test_8_repeated_runs_create_no_duplicates(db_session, papiliyana, make_branch):
    branch, user, p1, p2 = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 5), (p2, 1)])
    empty_branch = make_branch(branch_name="No History")

    first = auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    second = auto_order_service.auto_submit_missed_orders(db_session, now=NOW + timedelta(minutes=1))
    third = auto_order_service.auto_submit_missed_orders(db_session, now=NOW + timedelta(hours=3))

    assert [o.branch_id for o in first] == [branch.id]
    assert second == [] and third == []
    order = _today_order(db_session, branch)
    assert _lines(db_session, order) == {p1.id: 5.0, p2.id: 1.0}
    assert db_session.query(OrderLine).filter(OrderLine.order_id == order.id).count() == 2
    notices = db_session.query(MissedOrderNotice).filter(MissedOrderNotice.branch_id == empty_branch.id).all()
    assert len(notices) == 1
    submitted_audits = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "ORDER_AUTO_SUBMITTED", AuditLog.entity_id == order.id)
        .count()
    )
    assert submitted_audits == 1


# --------------------------------------------------------------------------
# Root-cause regression + eligibility
# --------------------------------------------------------------------------


def test_never_uses_a_different_weekday_even_if_more_recent(db_session, papiliyana):
    """The old fallback took the latest order on ANY weekday (here Wed 30 Sep) when last week's
    was missing — it must take Thu 17 Sep instead."""
    branch, user, p1, p2 = papiliyana
    _order(db_session, branch, user, date(2026, 9, 30), "SUBMITTED", [(p2, 1)])  # Wednesday
    _order(db_session, branch, user, date(2026, 9, 25), "SUBMITTED", [(p2, 1)])  # Friday
    thursday = _order(db_session, branch, user, SEP_17, "SUBMITTED", [(p1, 4)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.auto_source_order_id == thursday.id
    assert _lines(db_session, order) == {p1.id: 4.0}


def test_skips_ineligible_weeks_and_moves_one_more_week_back(db_session, papiliyana, make_product):
    branch, user, p1, _ = papiliyana
    gone = make_product(status="INACTIVE")
    _order(db_session, branch, user, SEP_24, "DRAFT", [(p1, 1)])  # never submitted
    _order(db_session, branch, user, SEP_17, "SUBMITTED", [(gone, 2)])  # nothing left to copy
    source = _order(db_session, branch, user, SEP_10, "SUBMITTED", [(p1, 6), (gone, 9)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.auto_source_order_id == source.id
    assert _lines(db_session, order) == {p1.id: 6.0}  # inactive product dropped


def test_stops_at_the_configured_lookback_limit(db_session, papiliyana, monkeypatch):
    branch, user, p1, _ = papiliyana
    monkeypatch.setattr(settings, "AUTO_SUBMIT_LOOKBACK_WEEKS", 2)
    _order(db_session, branch, user, SEP_10, "SUBMITTED", [(p1, 6)])  # 3 weeks back — out of range

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    assert _orders_on(db_session, branch, TODAY) == []
    assert branch.id in _open_notice_branch_ids(db_session)


def test_submits_unsent_draft_instead_of_history(db_session, papiliyana):
    branch, user, p1, p2 = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 5)])
    draft = _order(db_session, branch, user, TODAY, "DRAFT", [(p2, 3)])

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    order = _today_order(db_session, branch)
    assert order.id == draft.id
    assert order.status == "SUBMITTED"
    assert order.auto_submit_source == auto_order_service.SOURCE_DRAFT
    assert _lines(db_session, order) == {p2.id: 3.0}


def test_does_nothing_before_cutoff(db_session, papiliyana):
    branch, user, p1, _ = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 5)])

    assert auto_order_service.auto_submit_missed_orders(db_session, now=NOW.replace(hour=13, minute=59)) == []
    assert _orders_on(db_session, branch, TODAY) == []


def test_skips_branch_with_late_submission_exception(db_session, papiliyana, admin_user):
    branch, user, p1, _ = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 1)])
    db_session.add(OrderDeadlineException(branch_id=branch.id, order_date=TODAY, granted_by=admin_user.id))
    db_session.commit()

    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)

    assert _orders_on(db_session, branch, TODAY) == []


def test_concurrent_pass_does_nothing_while_another_holds_the_lock(db_session, db_engine, papiliyana):
    branch, user, p1, _ = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 1)])

    with db_engine.connect() as other_process:
        other_process.execute(text("SELECT pg_advisory_lock(:k)"), {"k": auto_order_service._ADVISORY_LOCK_KEY})
        try:
            assert auto_order_service.auto_submit_missed_orders(db_session, now=NOW) == []
        finally:
            other_process.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": auto_order_service._ADVISORY_LOCK_KEY})
            other_process.commit()
    assert _orders_on(db_session, branch, TODAY) == []

    # Lock released -> the next pass runs normally.
    assert [o.branch_id for o in auto_order_service.auto_submit_missed_orders(db_session, now=NOW)] == [branch.id]


# --------------------------------------------------------------------------
# Spec test 9: date calculations across month/year boundaries and leap years
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "order_date, expected",
    [
        (date(2026, 10, 1), [date(2026, 9, 24), date(2026, 9, 17), date(2026, 9, 10), date(2026, 9, 3)]),
        (date(2027, 1, 7), [date(2026, 12, 31), date(2026, 12, 24), date(2026, 12, 17), date(2026, 12, 10)]),
        (date(2028, 3, 7), [date(2028, 2, 29), date(2028, 2, 22), date(2028, 2, 15), date(2028, 2, 8)]),
        (date(2027, 3, 1), [date(2027, 2, 22), date(2027, 2, 15), date(2027, 2, 8), date(2027, 2, 1)]),
    ],
)
def test_9_fallback_dates_are_same_weekday_in_exact_7_day_steps(order_date, expected):
    dates = auto_order_service.fallback_source_dates(order_date, 4)
    assert dates == expected
    assert all(d.weekday() == order_date.weekday() for d in dates)
    assert all((a - b).days == 7 for a, b in zip([order_date] + dates, dates))


@pytest.mark.parametrize(
    "now, source_date, expected_delivery",
    [
        # year boundary: Thu 7 Jan 2027 copies Thu 31 Dec 2026
        (datetime(2027, 1, 7, 15, 0, tzinfo=BUSINESS_TZ), date(2026, 12, 31), date(2027, 1, 9)),
        # delivery crosses the year end
        (datetime(2026, 12, 30, 15, 0, tzinfo=BUSINESS_TZ), date(2026, 12, 23), date(2027, 1, 1)),
        # leap day as the source, and as the delivery date
        (datetime(2028, 3, 7, 15, 0, tzinfo=BUSINESS_TZ), date(2028, 2, 29), date(2028, 3, 9)),
        (datetime(2028, 2, 27, 15, 0, tzinfo=BUSINESS_TZ), date(2028, 2, 20), date(2028, 2, 29)),
        # month boundary in a non-leap year
        (datetime(2027, 3, 1, 15, 0, tzinfo=BUSINESS_TZ), date(2027, 2, 22), date(2027, 3, 3)),
    ],
)
def test_9_boundary_dates_end_to_end(db_session, papiliyana, now, source_date, expected_delivery):
    branch, user, p1, _ = papiliyana
    source = _order(db_session, branch, user, source_date, "SUBMITTED", [(p1, 2)])

    auto_order_service.auto_submit_missed_orders(db_session, now=now)

    order = _today_order(db_session, branch, today=now.date())
    assert order.auto_source_order_id == source.id
    assert order.delivery_date == expected_delivery


# --------------------------------------------------------------------------
# Admin follow-up
# --------------------------------------------------------------------------


def test_notice_clears_once_the_branch_has_an_order(db_session, papiliyana, admin_user):
    branch, _, p1, _ = papiliyana
    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    assert branch.id in _open_notice_branch_ids(db_session)

    order_service.admin_add_order_line(db_session, admin_user, branch.id, p1.id, TODAY + timedelta(days=2), 3)

    assert branch.id not in _open_notice_branch_ids(db_session)


def test_dismissing_a_notice(db_session, papiliyana, admin_user):
    branch, _, _, _ = papiliyana
    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    notice = db_session.query(MissedOrderNotice).filter(MissedOrderNotice.branch_id == branch.id).one()

    auto_order_service.mark_reviewed(db_session, admin_user, notice_id=notice.id)

    assert branch.id not in _open_notice_branch_ids(db_session)


def test_admin_can_remove_lines_from_auto_submitted_order_only(db_session, papiliyana, admin_user):
    branch, user, p1, p2 = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 5), (p2, 2)])
    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    order = _today_order(db_session, branch)

    order_service.admin_remove_order_line(db_session, admin_user, branch.id, p2.id, order.delivery_date)
    assert _lines(db_session, order) == {p1.id: 5.0}

    # The branch's own submitted order is still protected.
    with pytest.raises(ValidationFailedError):
        order_service.admin_remove_order_line(db_session, admin_user, branch.id, p1.id, SEP_24 + timedelta(days=2))


def test_review_clears_the_flag(db_session, papiliyana, admin_user):
    branch, user, p1, _ = papiliyana
    _order(db_session, branch, user, SEP_24, "SUBMITTED", [(p1, 5)])
    auto_order_service.auto_submit_missed_orders(db_session, now=NOW)
    order = _today_order(db_session, branch)
    assert order.id in {o.id for o in auto_order_service.list_unreviewed(db_session)}

    assert auto_order_service.mark_reviewed(db_session, admin_user, delivery_date=order.delivery_date) >= 1

    db_session.refresh(order)
    assert order.auto_reviewed_at is not None
    assert order.auto_reviewed_by == admin_user.id
