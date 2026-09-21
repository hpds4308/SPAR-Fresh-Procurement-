"""
QA: authorization matrix, generated from the FastAPI route table.

Three invariants that protect against the most common way an internal app
leaks data - a new route shipped without an auth/role dependency:

1. Every route except a short, explicit PUBLIC list answers 401 to an
   anonymous caller.
2. Every route that declares require_roles(...) answers 403 to an
   authenticated user whose role is not in the list.
3. The set of routes that need a login but NO specific role is exactly the
   whitelist below - adding one forces a conscious decision.
"""
import re

import pytest
from fastapi.routing import APIRoute

PUBLIC = {
    ("GET", "/"),
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/refresh"),
    ("POST", "/api/v1/auth/redeem-recovery-token"),
    ("GET", "/api/v1/settings"),  # intentionally public: cut-off times + support phone (settings.py:16-22)
}

# Any authenticated user (Admin, Branch or Supplier) may call these.
ANY_AUTHENTICATED = {
    ("POST", "/api/v1/auth/logout"),
    ("POST", "/api/v1/auth/change-password"),
    ("GET", "/api/v1/auth/me"),
    ("GET", "/api/v1/products"),
    ("GET", "/api/v1/orders/window"),
    ("GET", "/api/v1/orders"),          # scoped in the service: branch -> own rows, admin -> non-draft, supplier -> none
    ("GET", "/api/v1/orders/{order_id}"),  # scoped in the service (see test_authorization_db IDOR test)
    ("GET", "/api/v1/pricing/window"),
    ("GET", "/api/v1/settings"),
}


def _role_sets(route: APIRoute):
    """Return one set of allowed roles per require_roles(...) dependency found on the route."""
    found = []

    def walk(dep):
        call = dep.call
        code = getattr(call, "__code__", None)
        if code is not None and call.__qualname__.startswith("require_roles.<locals>"):
            closure = dict(zip(code.co_freevars, (c.cell_contents for c in call.__closure__ or ())))
            found.append(set(closure["allowed_roles"]))
        for sub in dep.dependencies:
            walk(sub)

    walk(route.dependant)
    return found


def _routes():
    from app.main import app

    out = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            for m in sorted(r.methods - {"HEAD", "OPTIONS"}):
                out.append((m, r.path, r))
    return out


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "1", path)


def _ids(params):
    return [f"{m} {p}" for m, p, _ in params]


ROUTES = _routes()
PROTECTED = [(m, p, r) for m, p, r in ROUTES if (m, p) not in PUBLIC]
ROLE_RESTRICTED = [(m, p, r) for m, p, r in PROTECTED if _role_sets(r)]


def test_route_table_is_not_empty():
    assert len(ROUTES) >= 85, "route introspection found suspiciously few routes"


@pytest.mark.parametrize("method,path,route", PROTECTED, ids=_ids(PROTECTED))
def test_anonymous_request_is_rejected_with_401(client_no_raise, method, path, route):
    r = client_no_raise.request(method, _concrete(path))
    assert r.status_code == 401, f"{method} {path} answered {r.status_code} to an anonymous caller"


@pytest.mark.parametrize("method,path,route", ROLE_RESTRICTED, ids=_ids(ROLE_RESTRICTED))
def test_wrong_role_is_rejected_with_403(
    client_no_raise, auth_headers, make_user, make_branch, make_supplier, method, path, route
):
    users = {
        "ADMIN": make_user(role="ADMIN"),
        "BRANCH": make_user(role="BRANCH", branch=make_branch()),
        "SUPPLIER": make_user(role="SUPPLIER", supplier=make_supplier()),
    }
    role_sets = _role_sets(route)
    for role, user in users.items():
        permitted = all(role in s for s in role_sets)
        if permitted:
            continue
        r = client_no_raise.request(method, _concrete(path), headers=auth_headers(user))
        assert r.status_code == 403, f"{role} got {r.status_code} on {method} {path}; expected 403"


def test_only_whitelisted_routes_are_open_to_every_authenticated_role():
    unrestricted = {(m, p) for m, p, r in PROTECTED if not _role_sets(r)}
    unexpected = unrestricted - ANY_AUTHENTICATED
    missing = ANY_AUTHENTICATED - unrestricted - PUBLIC
    assert not unexpected, f"routes with login-only protection (no role check) that are not whitelisted: {sorted(unexpected)}"
    assert not missing, f"whitelist entries that no longer exist / gained a role check: {sorted(missing)}"


def test_supplier_cannot_list_branch_orders(client, auth_headers, make_user, make_supplier, make_branch, make_product, db_session):
    """Row-level scoping on the one 'any role' list endpoint: a supplier must see zero branch orders."""
    from datetime import date, timedelta
    from app.models.order import Order

    branch_user = make_user(role="BRANCH", branch=make_branch())
    supplier_user = make_user(role="SUPPLIER", supplier=make_supplier())
    db_session.add(Order(branch_id=branch_user.branch_id, submitted_by=branch_user.id, order_date=date.today(),
                         delivery_date=date.today() + timedelta(days=2), status="SUBMITTED"))
    db_session.commit()
    r = client.get("/api/v1/orders", headers=auth_headers(supplier_user))
    assert r.status_code == 200 and r.json() == []


def test_public_settings_endpoint_exposes_only_non_sensitive_fields(client):
    body = client.get("/api/v1/settings").json()
    assert set(body) == {"branch_order_deadline", "supplier_price_deadline", "support_phone"}

