"""
Covers the same invariants scripts/smoke_test.py checks against a live
server ("order window delivery_date == order date + 2", cutoff gating),
but as a fast, deterministic unit test — no server or database needed.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings as env_settings
from app.services import order_service
from tests.conftest import FakeDB

BUSINESS_TZ = ZoneInfo("Asia/Colombo")


def _cutoff() -> time:
    hh, mm = env_settings.BRANCH_ORDER_DEADLINE.split(":")
    return time(hour=int(hh), minute=int(mm))


def test_delivery_date_is_always_two_days_after_order_date():
    db = FakeDB()
    now = datetime(2026, 6, 15, 9, 0, tzinfo=BUSINESS_TZ)
    window = order_service.get_order_window(db, now=now)
    assert window.delivery_date == now.date() + timedelta(days=2)


def test_open_just_before_cutoff():
    db = FakeDB()
    cutoff = _cutoff()
    just_before = datetime.combine(
        datetime(2026, 6, 15).date(), cutoff, tzinfo=BUSINESS_TZ
    ) - timedelta(minutes=1)
    window = order_service.get_order_window(db, now=just_before)
    assert window.is_open is True


def test_closed_at_and_after_cutoff():
    db = FakeDB()
    cutoff = _cutoff()
    at_cutoff = datetime.combine(datetime(2026, 6, 15).date(), cutoff, tzinfo=BUSINESS_TZ)
    window = order_service.get_order_window(db, now=at_cutoff)
    assert window.is_open is False

    after_cutoff = at_cutoff + timedelta(minutes=1)
    window2 = order_service.get_order_window(db, now=after_cutoff)
    assert window2.is_open is False


def test_cutoff_time_reflects_the_configured_deadline():
    db = FakeDB()
    now = datetime(2026, 6, 15, 9, 0, tzinfo=BUSINESS_TZ)
    window = order_service.get_order_window(db, now=now)
    assert window.cutoff_time == env_settings.BRANCH_ORDER_DEADLINE
