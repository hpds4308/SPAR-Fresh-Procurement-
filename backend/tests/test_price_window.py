"""
Covers the same invariant scripts/smoke_test.py checks against a live
server ("price window delivery_date == today + 2"), but as a fast,
deterministic unit test.
"""
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings as env_settings
from app.services import pricing_service
from tests.conftest import FakeDB

BUSINESS_TZ = ZoneInfo("Asia/Colombo")


def _cutoff() -> time:
    hh, mm = env_settings.SUPPLIER_PRICE_DEADLINE.split(":")
    return time(hour=int(hh), minute=int(mm))


def test_delivery_date_is_two_days_after_submission():
    db = FakeDB()
    now = datetime(2026, 6, 15, 9, 0, tzinfo=BUSINESS_TZ)
    window = pricing_service.get_price_window(db, now=now)
    assert window.delivery_date == now.date() + timedelta(days=2)


def test_open_just_before_cutoff():
    db = FakeDB()
    cutoff = _cutoff()
    just_before = datetime.combine(
        datetime(2026, 6, 15).date(), cutoff, tzinfo=BUSINESS_TZ
    ) - timedelta(minutes=1)
    window = pricing_service.get_price_window(db, now=just_before)
    assert window.is_open is True


def test_closed_at_and_after_cutoff():
    db = FakeDB()
    cutoff = _cutoff()
    at_cutoff = datetime.combine(datetime(2026, 6, 15).date(), cutoff, tzinfo=BUSINESS_TZ)
    window = pricing_service.get_price_window(db, now=at_cutoff)
    assert window.is_open is False

    after_cutoff = at_cutoff + timedelta(minutes=1)
    window2 = pricing_service.get_price_window(db, now=after_cutoff)
    assert window2.is_open is False


def test_pricing_and_order_delivery_dates_line_up():
    """
    Branch orders and supplier prices submitted on the same day both
    target the same future delivery date (submission date + 2) — that's
    what lets Admin match what was ordered against what suppliers quoted
    for the same delivery day. These drifting apart would silently break
    that comparison across the whole app.
    """
    from app.services import order_service

    db = FakeDB()
    now = datetime(2026, 6, 15, 9, 0, tzinfo=BUSINESS_TZ)
    order_window = order_service.get_order_window(db, now=now)
    price_window = pricing_service.get_price_window(db, now=now)
    assert price_window.delivery_date == order_window.delivery_date
