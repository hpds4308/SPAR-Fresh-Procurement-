"""
Regression tests for the fixes to SEC-02 (Excel upload bounds) and SEC-03 / BUG-07 (POS resilience).
"""
import urllib.error

import pytest

from app.services import pos_stock_service as pos
from test_qa_orders_and_validation import _row_flood_xlsx, _upload, _xlsx


# ------------------------------------------------------------------ SEC-02
def test_sec02_declared_unpacked_size_is_checked_before_parsing(client, auth_headers, make_user, make_branch, monkeypatch):
    """A few KB on the wire can unpack to hundreds of MB; judge by the zip's declared size, not the upload size."""
    from app.services import order_service

    user = make_user(role="BRANCH", branch=make_branch())
    data = _row_flood_xlsx(20_000)
    monkeypatch.setattr(order_service, "MAX_EXCEL_UNCOMPRESSED_BYTES", 100_000)  # a real 25 MB file is slow to build here
    called = {"n": 0}
    real_load = order_service.openpyxl.load_workbook

    def spy(*a, **k):
        called["n"] += 1
        return real_load(*a, **k)

    monkeypatch.setattr(order_service.openpyxl, "load_workbook", spy)
    r = _upload(client, auth_headers(user), data)
    assert r.status_code == 422 and called["n"] == 0  # rejected before openpyxl ever opened it


def test_sec02_blank_but_formatted_rows_are_bounded_too(client, auth_headers, make_user, make_branch, monkeypatch):
    """Excel 'used range' bloat is common; rows with no product code are skipped, but only up to a cap."""
    from app.services import order_service

    user = make_user(role="BRANCH", branch=make_branch())
    monkeypatch.setattr(order_service, "MAX_EXCEL_ROWS_SCANNED", 500)
    rows = [["", "", "", "", None] for _ in range(600)]
    assert _upload(client, auth_headers(user), _xlsx(rows)).status_code == 422


def test_sec02_a_real_sized_template_still_works(client, auth_headers, make_user, make_branch, make_product):
    user = make_user(role="BRANCH", branch=make_branch())
    products = [make_product() for _ in range(190)]
    rows = [[p.product_code, "", p.description, "kg", 3] for p in products] + [["", "", "", "", None] for _ in range(300)]
    r = _upload(client, auth_headers(user), _xlsx(rows))
    assert r.status_code == 200 and r.json()["valid_line_count"] == 190


def test_sec02_line_cap_boundary(client, auth_headers, make_user, make_branch, monkeypatch):
    from app.services import order_service

    user = make_user(role="BRANCH", branch=make_branch())
    monkeypatch.setattr(order_service, "MAX_EXCEL_ORDER_ROWS", 50)
    ok = _upload(client, auth_headers(user), _xlsx([[f"NOPE{i}", "", "", "kg", 1] for i in range(50)]))
    too_many = _upload(client, auth_headers(user), _xlsx([[f"NOPE{i}", "", "", "kg", 1] for i in range(51)]))
    assert ok.status_code == 200 and len(ok.json()["lines"]) == 50
    assert too_many.status_code == 422


def test_sec02_parsing_runs_off_the_event_loop_and_reads_a_bounded_amount():
    """The route is `async`: parsing inline froze every other request while a big sheet was processed."""
    import inspect

    from app.api.v1 import orders as orders_api

    source = inspect.getsource(orders_api.preview_order_excel)
    assert "run_in_threadpool(order_service.parse_order_excel" in source
    assert "file.read(MAX_ORDER_EXCEL_BYTES + 1)" in source  # never buffers more than limit + 1 byte


# ------------------------------------------------------------------ SEC-03 / BUG-07
@pytest.fixture()
def pos_configured(monkeypatch):
    monkeypatch.setattr(pos.settings, "POS_API_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(pos.settings, "POS_API_USERNAME", "u")
    monkeypatch.setattr(pos.settings, "POS_API_PASSWORD", "p")
    monkeypatch.setattr(pos, "_cached_token", None)
    monkeypatch.setattr(pos, "_cached_token_expires_at", 0.0)
    monkeypatch.setattr(pos, "_breaker_open_until", 0.0)


def test_breaker_reopens_the_pos_after_the_cooldown(pos_configured, monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr(pos.time, "monotonic", lambda: clock["t"])
    calls = {"n": 0}

    def fail(*a, **k):
        calls["n"] += 1
        raise urllib.error.URLError("down")

    monkeypatch.setattr(pos.urllib.request, "urlopen", fail)
    pos.get_stock_in_hand(["P1"], "00019")
    pos.get_stock_in_hand(["P1"], "00019")
    assert calls["n"] == 1  # second call short-circuited
    clock["t"] += pos.FAILURE_COOLDOWN_SECONDS + 1
    pos.get_stock_in_hand(["P1"], "00019")
    assert calls["n"] == 2  # cooldown over -> the POS gets another chance


def test_a_failure_forgets_the_cached_token(pos_configured, monkeypatch):
    monkeypatch.setattr(pos, "_cached_token", "stale")
    monkeypatch.setattr(pos, "_cached_token_expires_at", 9e12)

    def boom(*a, **k):
        raise ConnectionResetError("reset")

    monkeypatch.setattr(pos, "_post_json", boom)
    assert pos.get_stock_in_hand(["P1"], "00019") == {}
    assert pos._cached_token is None


def test_concurrent_pos_calls_are_capped(pos_configured, monkeypatch):
    """With every slot taken, further callers get {} at once instead of queueing behind a slow POS."""
    monkeypatch.setattr(pos, "_get_token", lambda: "tok")
    called = {"n": 0}

    def fake_post(*a, **k):
        called["n"] += 1
        return {"Data": []}

    monkeypatch.setattr(pos, "_post_json", fake_post)
    for _ in range(pos.MAX_CONCURRENT_POS_CALLS):
        assert pos._slots.acquire(blocking=False)
    try:
        assert pos.get_stock_in_hand(["P1"], "00019") == {}
        assert called["n"] == 0
    finally:
        for _ in range(pos.MAX_CONCURRENT_POS_CALLS):
            pos._slots.release()
    pos.get_stock_in_hand(["P1"], "00019")
    assert called["n"] == 1  # slots freed -> works again


def test_slot_is_released_even_when_the_call_blows_up(pos_configured, monkeypatch):
    monkeypatch.setattr(pos, "_get_token", lambda: "tok")

    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(pos, "_post_json", boom)
    with pytest.raises(RuntimeError):
        pos.get_stock_in_hand(["P1"], "00019")
    for _ in range(pos.MAX_CONCURRENT_POS_CALLS):  # every slot is still available
        assert pos._slots.acquire(blocking=False)
    for _ in range(pos.MAX_CONCURRENT_POS_CALLS):
        pos._slots.release()


def test_db_connection_is_handed_back_before_the_outbound_pos_call(pos_configured, db_session, make_user, make_branch, make_product, monkeypatch):
    """SEC-03: the session must not sit on a pooled connection while waiting for the POS."""
    from app.services import order_service

    branch = make_branch(pos_location_code="00019")
    user = make_user(role="BRANCH", branch=branch)
    make_product(pos_code="P1")
    seen = {}

    def spy(codes, location):
        seen["in_transaction"] = db_session.in_transaction()
        return {}

    monkeypatch.setattr(pos, "get_stock_in_hand", spy)
    order_service.get_stock_in_hand_for_branch(db_session, user)
    assert seen == {"in_transaction": False}
