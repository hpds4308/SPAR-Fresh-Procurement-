"""
Concurrency / resilience probes against a LOCAL stack (stdlib only).

  python qa/perf/concurrency_check.py orders  [BASE]   13 branches submit their daily order at the same instant,
                                                       plus a same-branch double-submit race
  python qa/perf/concurrency_check.py posdown [BASE]   AI-provider-outage analogue: the POS integration hangs;
                                                       how badly does /orders/stock-in-hand starve the rest of the API?

BASE defaults to http://127.0.0.1:8001/api/v1 (a backend started with the login/global rate limiter disabled,
so capacity - not the limiter - is what gets measured). For `posdown` start the backend with POS_API_BASE_URL
pointing at a server that accepts connections and never replies (see qa/README.md).
Never point this at production.
"""
import json
import statistics
import sys
import threading
import time
import urllib.error
import urllib.request

PASSWORD = "ChangeMe123!"


def call(base, method, path, token=None, body=None, timeout=60):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={
        "Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null"), time.perf_counter() - t0
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw), time.perf_counter() - t0
        except Exception:
            return e.code, raw[:200], time.perf_counter() - t0
    except Exception as e:  # timeout / reset
        return 0, repr(e), time.perf_counter() - t0


def login(base, user):
    s, b, _ = call(base, "POST", "/auth/login", body={"username": user, "password": PASSWORD})
    assert s == 200, f"login {user}: {s} {b}"
    return b["access_token"]


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


def orders(base):
    admin = login(base, "admin")
    call(base, "PUT", "/settings/branch_order_deadline", admin, {"value": "23:59"})
    products = call(base, "GET", "/products", admin)[1][:60]
    lines = [{"product_id": p["id"], "quantity": 5} for p in products]
    users = [f"br{i:02d}" for i in range(1, 14)]
    tokens = {u: login(base, u) for u in users}

    # True race: br13 has NOT ordered yet; two requests carry its first submission at the same instant.
    print("== first-submission race: br13 sends 2 simultaneous POST /orders (no order exists yet)")
    race, gate = [], threading.Barrier(2)

    def first():
        gate.wait()
        race.append(call(base, "POST", "/orders", tokens["br13"], {"lines": lines}))

    ts = [threading.Thread(target=first) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    print(f"   statuses={sorted(r[0] for r in race)}  (expected [200, 422]; two 200s = duplicate order, any 500 = unhandled race)")
    print(f"   orders visible to br13: {len(call(base, 'GET', '/orders', tokens['br13'])[1])} (expected 1)")

    print(f"== 13 branches submit a {len(lines)}-line order at the same instant")
    results, barrier = {}, threading.Barrier(len(users))

    def submit(u):
        barrier.wait()
        results[u] = call(base, "POST", "/orders", tokens[u], {"lines": lines})

    ts = [threading.Thread(target=submit, args=(u,)) for u in users]
    [t.start() for t in ts]
    [t.join() for t in ts]
    codes = [r[0] for r in results.values()]
    lat = [r[2] for r in results.values()]
    print(f"   statuses={sorted(set(codes))} ok={codes.count(200)}/13  latency p50={statistics.median(lat)*1000:.0f}ms max={max(lat)*1000:.0f}ms")
    already = [u for u, r in results.items() if r[0] == 422]
    if already:
        print(f"   (422 for {already}: they already had an order today - run qa/reset_qa_db.py for a clean run)")



def posdown(base):
    admin = login(base, "admin")
    br = login(base, "br03")
    branches = call(base, "GET", "/branches", admin)[1]
    b = next(x for x in branches if x["branch_code"].lower() == "br03")
    call(base, "PATCH", f"/branches/{b['id']}/pos-location-code", admin, {"pos_location_code": "00019"})

    print("== baseline (POS integration idle)")
    print(f"   /health {call(base, 'GET', '/health')[2]*1000:.0f}ms   login {call(base, 'POST', '/auth/login', body={'username': 'br04', 'password': PASSWORD})[2]*1000:.0f}ms")

    n = 45
    print(f"== {n} branch users open the New Order page while the POS hangs (15s timeout per call, default worker pool = 40 threads)")
    stock, done = [], threading.Event()

    def hit():
        stock.append(call(base, "GET", "/orders/stock-in-hand", br, timeout=90))

    ts = [threading.Thread(target=hit) for _ in range(n)]
    t0 = time.perf_counter()
    [t.start() for t in ts]
    time.sleep(1.5)
    probes = []
    for _ in range(4):
        h = call(base, "GET", "/health", timeout=60)
        l = call(base, "POST", "/auth/login", body={"username": "br04", "password": PASSWORD}, timeout=60)
        probes.append((time.perf_counter() - t0, h[0], h[2], l[0], l[2]))
        time.sleep(0.5)
    [t.join() for t in ts]
    print("   while stuck:  t(s)  /health(status, s)   login(status, s)")
    for t, hs, hl, ls, ll in probes:
        print(f"                 {t:5.1f}   {hs} {hl:6.2f}          {ls} {ll:6.2f}")
    lat = [s[2] for s in stock]
    print(f"   stock-in-hand: statuses={sorted(set(s[0] for s in stock))} p50={statistics.median(lat):.1f}s max={max(lat):.1f}s")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "orders"
    base = sys.argv[2] if len(sys.argv) > 2 else ("http://127.0.0.1:8002/api/v1" if mode == "posdown" else "http://127.0.0.1:8001/api/v1")
    if "127.0.0.1" not in base and "localhost" not in base:
        sys.exit("Refusing to run against a non-local host.")
    {"orders": orders, "posdown": posdown}[mode](base)
