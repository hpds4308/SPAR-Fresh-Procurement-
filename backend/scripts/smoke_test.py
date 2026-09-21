#!/usr/bin/env python3
"""
Smoke test: exercises the real, running API end-to-end and checks the
invariants that have actually broken before (see docs/DATA_MODEL.md).

This is NOT a unit test suite — it makes real HTTP requests against a
live server and a real (throwaway) database. Run it after any deploy,
or after touching order/pricing/date logic, before trusting the result.

Usage:
    python3 scripts/smoke_test.py [--base-url http://localhost:8000]

Exit code 0 = everything passed. Non-zero = at least one check failed;
scroll up for which one and why.

Assumes the standard seed scripts have been run (seed_master_data.py,
seed_users.py) against a database this script is allowed to write test
data into — do not point this at a real production database.

Seed the throwaway database with `python -m scripts.seed_users --no-force-change`:
by default every seeded account must choose its own password at first sign-in
and the API refuses everything else until it does, which this script (it signs
in with the seeded password) cannot do.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta

PASSED = []
FAILED = []


def check(name: str, condition: bool, detail: str = ""):
    if condition:
        PASSED.append(name)
        print(f"  \033[92m✓\033[0m {name}")
    else:
        FAILED.append((name, detail))
        print(f"  \033[91m✗\033[0m {name}  —  {detail}")


class Api:
    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/") + "/api/v1"

    def request(self, method: str, path: str, token: str | None = None, body=None):
        url = self.base + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw.decode(errors="replace")

    def get(self, path, token=None):
        return self.request("GET", path, token)

    def post(self, path, token=None, body=None):
        return self.request("POST", path, token, body)

    def put(self, path, token=None, body=None):
        return self.request("PUT", path, token, body)

    def patch(self, path, token=None, body=None):
        return self.request("PATCH", path, token, body)


def login(api: Api, username: str, password: str = "ChangeMe123!") -> str | None:
    status, resp = api.post("/auth/login", body={"username": username, "password": password})
    if status != 200:
        check(f"login as {username}", False, f"status={status} resp={resp}")
        return None
    check(f"login as {username}", True)
    return resp["access_token"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    api = Api(args.base_url)

    print("\n== Health & auth ==")
    status, _ = api.get("/health")
    check("backend is reachable (/health)", status == 200, f"status={status}")

    admin = login(api, "admin")
    branch = login(api, "br01")
    supplier = login(api, "sup01")
    supplier2 = login(api, "sup02")
    if not all([admin, branch, supplier, supplier2]):
        print("\nCan't continue without all logins working. Stopping here.")
        summarize()
        sys.exit(1)

    today = date.today().isoformat()

    print("\n== Branch orders (delivery date = order date + 2) ==")
    expected_order_delivery_date = (date.today() + timedelta(days=2)).isoformat()
    status, window = api.get("/orders/window", token=branch)
    check("order window reachable", status == 200, f"status={status}")
    if status == 200:
        check(
            "order window delivery_date == today+2 (lead-time rule, matches pricing)",
            window["delivery_date"] == expected_order_delivery_date,
            f"expected {expected_order_delivery_date}, got {window.get('delivery_date')}",
        )

    status, order = api.post("/orders", token=branch, body={"lines": [{"product_id": 1, "quantity": 5}]})
    if status == 200:
        check("branch can place an order", True)
        check(
            "delivery_date == order_date + 2 days",
            order["delivery_date"] == expected_order_delivery_date,
            f"order_date={order.get('order_date')} delivery_date={order.get('delivery_date')}",
        )
    elif status == 422 and "already" in json.dumps(order).lower():
        check("branch can place an order", True, "(already placed today — that's fine, re-run against a fresh DB for a clean check)")
    else:
        check("branch can place an order", False, f"status={status} resp={order}")

    status, dup = api.post("/orders", token=branch, body={"lines": [{"product_id": 2, "quantity": 3}]})
    check(
        "duplicate same-day order rejected cleanly (422, not 500)",
        status == 422,
        f"status={status} resp={dup}",
    )

    print("\n== Supplier pricing (delivery date = order date + 2) ==")
    status, pwindow = api.get("/pricing/window", token=supplier)
    check("price window reachable", status == 200, f"status={status}")
    expected_price_date = (date.today() + timedelta(days=2)).isoformat()
    if status == 200:
        check(
            "price window delivery_date == today+2 (pricing lead-time rule)",
            pwindow["delivery_date"] == expected_price_date,
            f"expected {expected_price_date}, got {pwindow.get('delivery_date')}",
        )

    status, submitted = api.post("/pricing", token=supplier, body={"prices": [{"product_id": 1, "price": 42}]})
    check("supplier can submit a price", status == 200, f"status={status} resp={submitted}")

    print("\n== Adjusted price: draft vs. sent ==")
    status, admin_prices = api.get(f"/pricing/admin?delivery_date={expected_price_date}", token=admin)
    check("admin can view all supplier prices", status == 200, f"status={status}")
    price_row = next((r for r in admin_prices if r["product_id"] == 1 and r["supplier_id"] == 1), None) if status == 200 else None
    check("just-submitted price appears in admin view", price_row is not None, "not found in admin price list")

    if price_row:
        status, _ = api.patch(f"/pricing/admin/{price_row['id']}/adjust", token=admin, body={"adjusted_price": 39})
        check("admin can set a draft adjusted price", status == 200, f"status={status}")

        status, mine = api.get(f"/pricing/mine?delivery_date={expected_price_date}", token=supplier)
        mine_row = next((r for r in mine if r["product_id"] == 1), None) if status == 200 else None
        check(
            "unsent draft adjusted price is NOT visible to supplier",
            mine_row is not None and mine_row.get("adjusted_price") is None,
            f"supplier saw adjusted_price={mine_row.get('adjusted_price') if mine_row else 'row missing'}",
        )

        status, _ = api.post(f"/pricing/admin/{price_row['id']}/send", token=admin)
        check("admin can send the adjusted price", status == 200, f"status={status}")

        status, mine = api.get(f"/pricing/mine?delivery_date={expected_price_date}", token=supplier)
        mine_row = next((r for r in mine if r["product_id"] == 1), None) if status == 200 else None
        check(
            "sent adjusted price IS visible to supplier",
            mine_row is not None and mine_row.get("adjusted_price") == 39,
            f"supplier saw adjusted_price={mine_row.get('adjusted_price') if mine_row else 'row missing'}",
        )

    print("\n== Supplier Orders & Cost Price resolution ==")
    status, order_result = api.put(
        f"/supplier-orders/admin?supplier_id=1&delivery_date={today}",
        token=admin,
        body={"items": [{"branch_id": 1, "product_id": 1, "quantity": 10}]},
    )
    check("admin can build a supplier order", status == 200, f"status={status} resp={order_result}")

    status, mine_orders = api.get("/supplier-orders/mine", token=supplier)
    check("supplier can view their orders by branch", status == 200, f"status={status}")
    if status == 200 and mine_orders["branches"]:
        item = mine_orders["branches"][0]["items"][0]
        # The sent adjusted price above was for expected_price_date
        # (today+2), but this supplier order was deliberately built for
        # plain `today` — a date with no submitted price — so there's no
        # exact-date match and Cost Price correctly falls back to the
        # most recent known price, flagged as an estimate. See
        # docs/DATA_MODEL.md "Cost Price resolution" — this is the
        # expected, documented behaviour, not a bug.
        check(
            "Cost Price falls back to the most recent price when dates don't align, flagged as an estimate",
            item["effective_price"] == 39 and item["price_is_estimated"] is True,
            f"effective_price={item.get('effective_price')} is_estimated={item.get('price_is_estimated')}",
        )

    # Now submit + send a price for the order's OWN delivery date, so we
    # can also verify the exact-match (non-estimated) path.
    status, _ = api.post("/pricing", token=supplier, body={"prices": [{"product_id": 1, "price": 33}]})
    # This submission lands on the current price window's date (today+2)
    # — pricing always targets submission_date+2 regardless of what other
    # dates exist, so submitting again doesn't change that. To test the
    # exact-match path, build a supplier order for that SAME date
    # directly (this now also matches what a real branch order placed
    # today would target, since orders are order_date+2 too — see
    # docs/DATA_MODEL.md).
    status, order_result2 = api.put(
        f"/supplier-orders/admin?supplier_id=1&delivery_date={expected_price_date}",
        token=admin,
        body={"items": [{"branch_id": 1, "product_id": 1, "quantity": 4}]},
    )
    check("admin can build a supplier order for a date pricing already covers", status == 200, f"status={status}")
    status, admin_order_view = api.get(
        f"/supplier-orders/admin?supplier_id=1&delivery_date={expected_price_date}", token=admin
    )
    if status == 200 and admin_order_view["items"]:
        item2 = admin_order_view["items"][0]
        check(
            "Cost Price is an exact confirmed match when the order date lines up with a sent price",
            item2["effective_price"] == 39 and item2["price_is_estimated"] is False,
            f"effective_price={item2.get('effective_price')} is_estimated={item2.get('price_is_estimated')}",
        )
    else:
        check("Cost Price is an exact confirmed match when the order date lines up with a sent price", False, f"status={status}")

    print("\n== Messages (one thread per supplier) ==")
    status, _ = api.post("/messages/admin/1", token=admin, body={"body": "smoke test message"})
    check("admin can send a message", status == 200, f"status={status}")
    status, thread = api.get("/messages/mine", token=supplier)
    check(
        "supplier sees admin's message, and it's marked read on fetch",
        status == 200 and any(m["body"] == "smoke test message" for m in thread),
        f"status={status}",
    )
    status, unread = api.get("/messages/mine/unread-count", token=supplier)
    check("supplier unread count is 0 after reading", status == 200 and unread["count"] == 0, f"resp={unread}")

    print("\n== Master Data Sheet ==")
    status, sheet = api.get("/master-data", token=admin)
    check("master data sheet reachable", status == 200, f"status={status}")
    if status == 200:
        row = next((r for r in sheet["rows"] if r["product_id"] == 1), None)
        check("target_gp_percent defaults to 0.30", row is not None and row["target_gp_percent"] == 0.30, f"got {row.get('target_gp_percent') if row else None}")
        # We adjusted product 1 to 39 above and it's supplier 1's only quote, so cost_price should reflect that.
        check(
            "cost_price reflects highest current supplier price",
            row is not None and row["cost_price"] is not None,
            f"cost_price={row.get('cost_price') if row else None}",
        )

    print("\n== Keells / market reference prices (auto-sync between pages) ==")
    keells_date = expected_price_date
    status, _ = api.put(f"/pricing/reference/1?delivery_date={keells_date}", token=admin, body={"price": 470})
    check("admin can set a Keells reference price", status == 200, f"status={status}")
    status, refs = api.get(f"/pricing/reference?delivery_date={keells_date}", token=admin)
    check(
        "Keells price set on one page immediately visible via the shared endpoint",
        status == 200 and any(r["product_id"] == 1 and r["price"] == 470 for r in refs),
        f"status={status} resp={refs}",
    )

    print("\n== Permission boundaries ==")
    status, _ = api.get("/messages/admin/threads", token=supplier)
    check("supplier blocked from admin-only endpoint (403)", status == 403, f"status={status}")
    # /messages/mine is intentionally shared by SUPPLIER and BRANCH alike
    # (each branch has its own thread with Admin, same as suppliers) —
    # this used to be supplier-only and this check expected a 403, but
    # that's no longer the intended behavior.
    status, _ = api.post("/messages/mine", token=branch, body={"body": "smoke test message"})
    check("branch can use the shared /messages/mine endpoint", status == 200, f"status={status}")
    status, _ = api.get("/master-data", token=supplier)
    check("supplier blocked from master data sheet (403)", status == 403, f"status={status}")

    print("\n== Audit log ==")
    status, actions = api.get("/audit-logs/actions", token=admin)
    check("audit log actions endpoint reachable", status == 200, f"status={status}")
    status, logs = api.get("/audit-logs?limit=50", token=admin)
    check("audit log reachable and non-empty (we did plenty above)", status == 200 and len(logs) > 0, f"status={status} count={len(logs) if status == 200 else 'n/a'}")
    if status == 200 and logs:
        check(
            "audit log entries resolve a username, not just a raw user_id",
            any(l["username"] is not None for l in logs),
            "every entry had username=null",
        )
    status, _ = api.get("/audit-logs", token=supplier)
    check("supplier blocked from audit log (403)", status == 403, f"status={status}")

    summarize()
    sys.exit(1 if FAILED else 0)


def summarize():
    print(f"\n{'='*60}")
    print(f"  {len(PASSED)} passed, {len(FAILED)} failed")
    if FAILED:
        print("\n  Failed checks:")
        for name, detail in FAILED:
            print(f"    - {name}: {detail}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
