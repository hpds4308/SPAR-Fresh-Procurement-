"""
DB-backed tests for admin Promotions — one promotion per product, shown to
branches only while today falls inside its date range.
"""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.core.errors import ValidationFailedError
from app.schemas.promotion import PromotionLineIn, PromotionSave
from app.services import promotion_service

TODAY = date(2026, 9, 25)


def _line(pid, ptype="FRESH_CHOICE", start=TODAY, end=TODAY):
    return PromotionLineIn(product_id=pid, promotion_type=ptype, start_date=start, end_date=end)


def test_save_replaces_previous_list(db_session, make_user, make_product):
    admin = make_user(role="ADMIN")
    a, b = make_product(), make_product()
    promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(a.id), _line(b.id, "SPECIAL")]))

    out = promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(b.id, "SPECIAL_WEEKEND")]))

    assert [(p.product_id, p.promotion_type) for p in out] == [(b.id, "SPECIAL_WEEKEND")]


def test_active_only_within_date_range(db_session, make_user, make_product):
    admin = make_user(role="ADMIN")
    running, ended, upcoming = make_product(), make_product(), make_product()
    promotion_service.save_all(
        db_session,
        admin,
        PromotionSave(
            lines=[
                _line(running.id, start=TODAY - timedelta(days=2), end=TODAY),
                _line(ended.id, start=TODAY - timedelta(days=5), end=TODAY - timedelta(days=1)),
                _line(upcoming.id, start=TODAY + timedelta(days=1), end=TODAY + timedelta(days=3)),
            ]
        ),
    )

    active = promotion_service.list_active(db_session, today=TODAY)

    assert [p.product_id for p in active] == [running.id]


def test_end_before_start_rejected():
    with pytest.raises(ValidationError):
        _line(1, start=TODAY, end=TODAY - timedelta(days=1))


def test_unknown_product_rejected(db_session, make_user):
    admin = make_user(role="ADMIN")
    with pytest.raises(ValidationFailedError):
        promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(999999)]))


def test_api_role_gates(client, make_branch, make_user, make_product, auth_headers):
    admin = make_user(role="ADMIN")
    branch = make_user(role="BRANCH", branch=make_branch())
    a = make_product()
    body = {"lines": [{"product_id": a.id, "promotion_type": "SPECIAL", "start_date": "2000-01-01", "end_date": "2999-12-31"}]}

    assert client.put("/api/v1/promotions", json=body, headers=auth_headers(branch)).status_code == 403
    r = client.put("/api/v1/promotions", json=body, headers=auth_headers(admin))
    assert r.status_code == 200, r.text

    r = client.get("/api/v1/promotions/active", headers=auth_headers(branch))
    assert r.status_code == 200
    assert [p["product_id"] for p in r.json()] == [a.id]
