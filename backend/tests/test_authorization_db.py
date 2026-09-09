"""
DB-backed authorization tests: every role (ADMIN, BRANCH, SUPPLIER) against
a representative slice of role-gated endpoints, plus unauthenticated
access. Covers H-4's "Authorization" category.

These hit the real HTTP layer (the `client` fixture) rather than calling
service functions directly, since the thing actually being verified here
is the routing/dependency wiring (Depends(require_roles(...))), not
business logic.
"""
import pytest


@pytest.fixture()
def admin(make_user):
    return make_user(role="ADMIN")


@pytest.fixture()
def branch_user(make_branch, make_user):
    return make_user(role="BRANCH", branch=make_branch())


@pytest.fixture()
def supplier_user(make_supplier, make_user):
    return make_user(role="SUPPLIER", supplier=make_supplier())


# --- Admin-only endpoints ---------------------------------------------------


@pytest.mark.parametrize("path", ["/api/v1/branches", "/api/v1/master-data", "/api/v1/orders/admin/matrix"])
def test_admin_only_endpoints_allow_admin(client, auth_headers, admin, path):
    resp = client.get(path, headers=auth_headers(admin))
    assert resp.status_code not in (401, 403)


@pytest.mark.parametrize("path", ["/api/v1/branches", "/api/v1/master-data", "/api/v1/orders/admin/matrix"])
def test_admin_only_endpoints_block_branch(client, auth_headers, branch_user, path):
    resp = client.get(path, headers=auth_headers(branch_user))
    assert resp.status_code == 403


@pytest.mark.parametrize("path", ["/api/v1/branches", "/api/v1/master-data", "/api/v1/orders/admin/matrix"])
def test_admin_only_endpoints_block_supplier(client, auth_headers, supplier_user, path):
    resp = client.get(path, headers=auth_headers(supplier_user))
    assert resp.status_code == 403


@pytest.mark.parametrize("path", ["/api/v1/branches", "/api/v1/master-data", "/api/v1/orders/admin/matrix"])
def test_admin_only_endpoints_block_unauthenticated(client, path):
    resp = client.get(path)
    assert resp.status_code == 401


# --- Branch-only endpoint ----------------------------------------------------


def test_branch_only_endpoint_allows_branch(client, auth_headers, branch_user):
    resp = client.get("/api/v1/orders/mine/today", headers=auth_headers(branch_user))
    assert resp.status_code not in (401, 403)


def test_branch_only_endpoint_blocks_admin(client, auth_headers, admin):
    resp = client.get("/api/v1/orders/mine/today", headers=auth_headers(admin))
    assert resp.status_code == 403


def test_branch_only_endpoint_blocks_supplier(client, auth_headers, supplier_user):
    resp = client.get("/api/v1/orders/mine/today", headers=auth_headers(supplier_user))
    assert resp.status_code == 403


# --- Supplier-only endpoint --------------------------------------------------


def test_supplier_only_endpoint_allows_supplier(client, auth_headers, supplier_user):
    resp = client.get("/api/v1/pricing/mine", headers=auth_headers(supplier_user))
    assert resp.status_code not in (401, 403)


def test_supplier_only_endpoint_blocks_branch(client, auth_headers, branch_user):
    resp = client.get("/api/v1/pricing/mine", headers=auth_headers(branch_user))
    assert resp.status_code == 403


def test_supplier_only_endpoint_blocks_admin(client, auth_headers, admin):
    resp = client.get("/api/v1/pricing/mine", headers=auth_headers(admin))
    assert resp.status_code == 403


# --- Any-authenticated-role endpoint ------------------------------------------


def test_shared_endpoint_allows_every_role(client, auth_headers, admin, branch_user, supplier_user):
    for user in (admin, branch_user, supplier_user):
        resp = client.get("/api/v1/orders/window", headers=auth_headers(user))
        assert resp.status_code == 200, f"role for user {user.username} was blocked unexpectedly"


# --- Inactive account is rejected regardless of a technically-valid token ---


def test_inactive_account_rejected_even_with_valid_token(client, auth_headers, make_branch, make_user):
    branch = make_branch()
    user = make_user(role="BRANCH", branch=branch, is_active=False)
    resp = client.get("/api/v1/orders/window", headers=auth_headers(user))
    assert resp.status_code == 401


# --- Cross-branch IDOR: a branch cannot read another branch's order --------


def test_branch_cannot_read_another_branchs_order(client, auth_headers, make_branch, make_user, make_product, db_session):
    from datetime import date, timedelta
    from app.models.order import Order, OrderLine
    from app.models.system import SystemSetting

    owner = make_user(role="BRANCH", branch=make_branch())
    intruder = make_user(role="BRANCH", branch=make_branch())
    product = make_product()
    db_session.add(SystemSetting(key="branch_order_deadline", value="23:59", updated_by=owner.id))
    db_session.commit()

    order = Order(
        branch_id=owner.branch_id,
        submitted_by=owner.id,
        order_date=date.today(),
        delivery_date=date.today() + timedelta(days=2),
        status="SUBMITTED",
    )
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderLine(order_id=order.id, product_id=product.id, quantity=1, unit_code="KG"))
    db_session.commit()

    resp = client.get(f"/api/v1/orders/{order.id}", headers=auth_headers(intruder))
    assert resp.status_code in (403, 404)
