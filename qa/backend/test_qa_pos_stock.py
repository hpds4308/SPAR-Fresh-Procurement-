"""
QA: POS "Stock in Hand" integration (services/pos_stock_service.py).

The module's contract (its own docstring, lines 1-15) is: every failure mode
degrades to "no stock shown", never an error to the branch user. These tests
use a REAL local TCP server (no network egress) to misbehave the way a flaky
vendor server does, plus mocks for the token step.

Evidence for BUG-07 (unhandled connection errors -> HTTP 500) and RISK-03
(no negative caching -> every page load waits on a dead POS).
"""
import http.client
import socket
import threading
import urllib.error

import pytest

from app.services import pos_stock_service as pos


@pytest.fixture()
def pos_configured(monkeypatch):
    monkeypatch.setattr(pos.settings, "POS_API_BASE_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(pos.settings, "POS_API_USERNAME", "u")
    monkeypatch.setattr(pos.settings, "POS_API_PASSWORD", "p")
    monkeypatch.setattr(pos, "_cached_token", None)
    monkeypatch.setattr(pos, "_cached_token_expires_at", 0.0)
    monkeypatch.setattr(pos, "_breaker_open_until", 0.0)  # the circuit breaker is process-global state


class _Server:
    """One-shot TCP server; `behaviour(conn)` decides how to (mis)behave."""

    def __init__(self, behaviour):
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(5)
        self.port = self.sock.getsockname()[1]
        self.hits = 0
        self._behaviour = behaviour
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    def _run(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.hits += 1
            try:
                self._behaviour(conn)
            finally:
                conn.close()

    def close(self):
        self.sock.close()


_HDR_END = bytes((13, 10, 13, 10))
_LINE_END = bytes((13, 10))


def _read_request(conn):
    """Consume one full HTTP request (headers + Content-Length body) so closing the socket
    afterwards sends a clean FIN instead of an RST that would mask the behaviour under test."""
    data = b""
    while _HDR_END not in data:
        chunk = conn.recv(4096)
        if not chunk:
            return
        data += chunk
    head, _, rest = data.partition(_HDR_END)
    length = 0
    for line in head.split(_LINE_END):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1])
    while len(rest) < length:
        chunk = conn.recv(4096)
        if not chunk:
            return
        rest += chunk


def _drop_immediately(conn):
    _read_request(conn)  # read the request, then hang up with no response


def _truncated_body(conn):
    _read_request(conn)
    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 500\r\nContent-Type: application/json\r\n\r\n{\"Data\": [")


def _json_200(conn):
    _read_request(conn)
    body = b'{"Data":[{"Products":[{"ProductCode":"P1","CurrentStockInHand":7.5}]}]}'
    conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body)


def _with_server(monkeypatch, behaviour):
    srv = _Server(behaviour)
    monkeypatch.setattr(pos.settings, "POS_API_BASE_URL", f"http://127.0.0.1:{srv.port}")
    monkeypatch.setattr(pos, "_cached_token", "tok")
    monkeypatch.setattr(pos, "_cached_token_expires_at", 9e12)
    return srv


# ------------------------------------------------------------------ passing behaviour
def test_not_configured_returns_empty_without_touching_network(monkeypatch):
    monkeypatch.setattr(pos.settings, "POS_API_BASE_URL", "")
    assert pos.get_stock_in_hand(["P1"], "00019") == {}


def test_happy_path_parses_stock_quantities(pos_configured, monkeypatch):
    srv = _with_server(monkeypatch, _json_200)
    try:
        assert pos.get_stock_in_hand(["P1"], "00019") == {"P1": 7.5}
    finally:
        srv.close()


def test_url_error_and_timeout_degrade_to_empty(pos_configured, monkeypatch):
    monkeypatch.setattr(pos, "_get_token", lambda: "tok")
    for exc in (urllib.error.URLError("dns"), TimeoutError("slow"), ValueError("bad json")):
        def boom(*a, _e=exc, **k):
            raise _e
        monkeypatch.setattr(pos, "_post_json", boom)
        assert pos.get_stock_in_hand(["P1"], "00019") == {}


# ------------------------------------------------------------------ BUG-07 (fixed): every failure mode degrades to {}
def test_bug07_server_hangup_degrades_to_empty(pos_configured, monkeypatch):
    srv = _with_server(monkeypatch, _drop_immediately)
    try:
        assert pos.get_stock_in_hand(["P1"], "00019") == {}
    finally:
        srv.close()


def test_bug07_truncated_response_degrades_to_empty(pos_configured, monkeypatch):
    srv = _with_server(monkeypatch, _truncated_body)
    try:
        assert pos.get_stock_in_hand(["P1"], "00019") == {}
    finally:
        srv.close()


def test_bug07_login_hangup_degrades_to_empty(pos_configured, monkeypatch):
    srv = _Server(_drop_immediately)
    monkeypatch.setattr(pos.settings, "POS_API_BASE_URL", f"http://127.0.0.1:{srv.port}")
    try:
        assert pos.get_stock_in_hand(["P1"], "00019") == {}
    finally:
        srv.close()


def test_bug07_endpoint_no_longer_returns_http_500(pos_configured, client_no_raise, auth_headers, make_user, make_branch, make_product, db_session, monkeypatch):
    """GET /orders/stock-in-hand used to answer 500 while the POS dropped connections; it must be a plain 200 {}."""
    branch = make_branch(pos_location_code="00019")
    user = make_user(role="BRANCH", branch=branch)
    make_product(pos_code="P1")
    srv = _with_server(monkeypatch, _drop_immediately)
    try:
        r = client_no_raise.get("/api/v1/orders/stock-in-hand", headers=auth_headers(user))
    finally:
        srv.close()
    assert r.status_code == 200 and r.json() == {}


# ------------------------------------------------------------------ RISK-03 / SEC-03 (fixed): a dead POS is left alone
def test_dead_pos_is_not_retried_on_every_request(pos_configured, monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(*a, **k):
        calls["n"] += 1
        raise urllib.error.URLError("unreachable")

    monkeypatch.setattr(pos.urllib.request, "urlopen", fake_urlopen)
    for _ in range(5):
        pos.get_stock_in_hand(["P1"], "00019")
    assert calls["n"] == 1, f"POS login was re-attempted {calls['n']} times in 5 back-to-back requests"
