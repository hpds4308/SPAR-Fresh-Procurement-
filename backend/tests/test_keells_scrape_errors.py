"""
Keells sync failures come back as KeellsScrapeError — a handled 502 with a
readable message — never as an unhandled 500, and never touch saved prices.
No real browser or network: pages are fakes.
"""
import pytest
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from app.core.errors import AppError
from app.services import keells_scrape_service as ks


class _Response:
    def __init__(self, status):
        self.status = status


class _Locator:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self

    def wait_for(self, **kwargs):
        raise PlaywrightTimeoutError("Locator.wait_for: Timeout 20000ms exceeded.")


class _FakePage:
    def __init__(self, status=200, body="", goto_error=None):
        self.status, self.body, self.goto_error = status, body, goto_error

    def goto(self, *args, **kwargs):
        if self.goto_error:
            raise self.goto_error
        return _Response(self.status)

    def locator(self, selector):
        return _Locator(self)

    def title(self):
        return ""

    def inner_text(self, selector, timeout=None):
        return self.body


def _scrape(page):
    return ks._scrape_category(page, ks.LOCAL_FRUITS_URL, "Local Fruits", needs_view_all=False)


def test_http_403_is_a_readable_502():
    with pytest.raises(ks.KeellsScrapeError) as e:
        _scrape(_FakePage(status=403))
    assert isinstance(e.value, AppError) and e.value.status_code == 502
    assert e.value.message == ks.BLOCKED_MESSAGE
    assert "Existing prices were not changed" in e.value.message


def test_security_check_page_without_403_still_reads_as_blocked():
    page = _FakePage(status=200, body="www.keellssuper.com Performing security verification ... Cloudflare")
    with pytest.raises(ks.KeellsScrapeError) as e:
        _scrape(page)
    assert e.value.message == ks.BLOCKED_MESSAGE


def test_product_timeout_is_a_readable_error():
    with pytest.raises(ks.KeellsScrapeError) as e:
        _scrape(_FakePage(status=200, body="Fruits Local Fruits"))
    assert e.value.message == ks.NO_PRODUCTS_MESSAGE


def test_navigation_error_is_a_readable_error():
    with pytest.raises(ks.KeellsScrapeError) as e:
        _scrape(_FakePage(goto_error=PlaywrightError("net::ERR_NAME_NOT_RESOLVED")))
    assert e.value.message == ks.UNREACHABLE_MESSAGE


@pytest.mark.parametrize("status", [500, 404])
def test_other_http_errors_are_readable(status):
    with pytest.raises(ks.KeellsScrapeError) as e:
        _scrape(_FakePage(status=status))
    assert e.value.message == ks.UNREACHABLE_MESSAGE


def test_messages_carry_no_technical_detail():
    for message in (ks.BLOCKED_MESSAGE, ks.UNREACHABLE_MESSAGE, ks.NO_PRODUCTS_MESSAGE, ks.NO_MATCHES_MESSAGE):
        assert "Traceback" not in message and "playwright" not in message.lower() and "/app/" not in message
