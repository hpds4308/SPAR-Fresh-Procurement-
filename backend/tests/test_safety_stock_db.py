"""
DB-backed tests for the branch Safety Stock list — one standing quantity
per (branch, product) that persists until the branch saves again or clears.
"""
import pytest

from app.core.errors import PermissionDeniedError, ValidationFailedError
from app.schemas.safety_stock import SafetyStockLineIn, SafetyStockSave
from app.services import safety_stock_service


def _save(db_session, user, pairs):
    payload = SafetyStockSave(lines=[SafetyStockLineIn(product_id=p, quantity=q) for p, q in pairs])
    return safety_stock_service.save_for_branch(db_session, user, payload)


def test_save_then_reload_returns_same_quantities(db_session, make_branch, make_user, make_product):
    user = make_user(role="BRANCH", branch=make_branch())
    a, b = make_product(), make_product()

    _save(db_session, user, [(a.id, 5), (b.id, 2.5)])

    out = safety_stock_service.get_for_branch(db_session, user)
    assert out.quantities == {a.id: 5.0, b.id: 2.5}
    assert out.updated_at is not None
    assert out.updated_by_username == user.username


def test_save_replaces_previous_list(db_session, make_branch, make_user, make_product):
    user = make_user(role="BRANCH", branch=make_branch())
    a, b = make_product(), make_product()
    _save(db_session, user, [(a.id, 5), (b.id, 3)])

    out = _save(db_session, user, [(a.id, 7)])

    assert out.quantities == {a.id: 7.0}


def test_empty_save_clears_all(db_session, make_branch, make_user, make_product):
    user = make_user(role="BRANCH", branch=make_branch())
    a = make_product()
    _save(db_session, user, [(a.id, 5)])

    out = _save(db_session, user, [])

    assert out.quantities == {}
    assert out.updated_at is None


def test_branches_are_isolated(db_session, make_branch, make_user, make_product):
    u1 = make_user(role="BRANCH", branch=make_branch())
    u2 = make_user(role="BRANCH", branch=make_branch())
    a = make_product()
    _save(db_session, u1, [(a.id, 5)])

    assert safety_stock_service.get_for_branch(db_session, u2).quantities == {}


def test_unknown_product_rejected(db_session, make_branch, make_user):
    user = make_user(role="BRANCH", branch=make_branch())
    with pytest.raises(ValidationFailedError):
        _save(db_session, user, [(999999, 1)])


def test_non_branch_user_rejected(db_session, make_user):
    admin = make_user(role="ADMIN")
    with pytest.raises(PermissionDeniedError):
        safety_stock_service.get_for_branch(db_session, admin)


def test_api_round_trip_and_role_gate(client, make_branch, make_user, make_product, auth_headers):
    user = make_user(role="BRANCH", branch=make_branch())
    admin = make_user(role="ADMIN")
    a = make_product()

    r = client.put("/api/v1/safety-stock/mine", json={"lines": [{"product_id": a.id, "quantity": 4}]}, headers=auth_headers(user))
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/safety-stock/mine", headers=auth_headers(user))
    assert r.json()["quantities"] == {str(a.id): 4.0}

    assert client.get("/api/v1/safety-stock/mine", headers=auth_headers(admin)).status_code == 403
