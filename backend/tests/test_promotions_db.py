"""
DB-backed tests for admin Promotions — Admin creates and deletes promotions
(name + color), sets one per product, and branches see it only while today
falls inside its date range.
"""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.core.errors import ConflictError, ValidationFailedError
from app.schemas.promotion import PromotionLineIn, PromotionSave, PromotionTypeIn
from app.services import promotion_service

TODAY = date(2026, 9, 25)


@pytest.fixture
def make_type(db_session, make_user):
    admin = make_user(role="ADMIN")
    counter = iter(range(1, 10_000))

    def _make(name=None, color="blue"):
        return promotion_service.create_type(
            db_session, admin, PromotionTypeIn(name=name or f"Promo {next(counter)}", color=color)
        )

    return _make


def _line(pid, type_id, start=TODAY, end=TODAY):
    return PromotionLineIn(product_id=pid, promotion_type_id=type_id, start_date=start, end_date=end)


def test_save_replaces_previous_list(db_session, make_user, make_product, make_type):
    admin = make_user(role="ADMIN")
    fresh, weekend = make_type(), make_type(color="green")
    a, b = make_product(), make_product()
    promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(a.id, fresh.id), _line(b.id, fresh.id)]))

    out = promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(b.id, weekend.id)]))

    assert [(p.product_id, p.promotion_type_id, p.promotion_name, p.color) for p in out] == [
        (b.id, weekend.id, weekend.name, "green")
    ]


def test_active_only_within_date_range(db_session, make_user, make_product, make_type):
    admin = make_user(role="ADMIN")
    t = make_type()
    running, ended, upcoming = make_product(), make_product(), make_product()
    promotion_service.save_all(
        db_session,
        admin,
        PromotionSave(
            lines=[
                _line(running.id, t.id, start=TODAY - timedelta(days=2), end=TODAY),
                _line(ended.id, t.id, start=TODAY - timedelta(days=5), end=TODAY - timedelta(days=1)),
                _line(upcoming.id, t.id, start=TODAY + timedelta(days=1), end=TODAY + timedelta(days=3)),
            ]
        ),
    )

    active = promotion_service.list_active(db_session, today=TODAY)

    assert [p.product_id for p in active] == [running.id]


def test_end_before_start_rejected():
    with pytest.raises(ValidationError):
        _line(1, 1, start=TODAY, end=TODAY - timedelta(days=1))


def test_unknown_product_rejected(db_session, make_user, make_type):
    admin = make_user(role="ADMIN")
    t = make_type()
    with pytest.raises(ValidationFailedError):
        promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(999999, t.id)]))


def test_unknown_promotion_type_rejected(db_session, make_user, make_product):
    admin = make_user(role="ADMIN")
    a = make_product()
    with pytest.raises(ValidationFailedError):
        promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(a.id, 999999)]))


def test_create_type_rejects_duplicate_name_ignoring_case(make_type):
    make_type("Avurudu Offer")
    with pytest.raises(ConflictError):
        make_type("  avurudu   OFFER ")


def test_blank_type_name_rejected():
    with pytest.raises(ValidationError):
        PromotionTypeIn(name="   ", color="red")


def test_delete_type_removes_it_from_products(db_session, make_user, make_product, make_type):
    admin = make_user(role="ADMIN")
    keep, drop = make_type(), make_type()
    a, b = make_product(), make_product()
    promotion_service.save_all(db_session, admin, PromotionSave(lines=[_line(a.id, keep.id), _line(b.id, drop.id)]))

    promotion_service.delete_type(db_session, admin, drop.id)

    assert [p.product_id for p in promotion_service.list_all(db_session)] == [a.id]
    counts = {t.id: t.product_count for t in promotion_service.list_types(db_session)}
    assert drop.id not in counts
    assert counts[keep.id] == 1


def test_built_in_promotions_are_seeded(db_session):
    names = {t.name for t in promotion_service.list_types(db_session)}
    assert {"Fresh Choice", "Special Weekend Promotion", "Special Promotion"} <= names


def test_api_role_gates(client, make_branch, make_user, make_product, auth_headers):
    admin = make_user(role="ADMIN")
    branch = make_user(role="BRANCH", branch=make_branch())
    a = make_product()

    new_type = {"name": "Mega Deal", "color": "purple"}
    assert client.post("/api/v1/promotions/types", json=new_type, headers=auth_headers(branch)).status_code == 403
    r = client.post("/api/v1/promotions/types", json=new_type, headers=auth_headers(admin))
    assert r.status_code == 201, r.text
    type_id = r.json()["id"]
    assert client.get("/api/v1/promotions/types", headers=auth_headers(branch)).status_code == 403

    body = {"lines": [{"product_id": a.id, "promotion_type_id": type_id, "start_date": "2000-01-01", "end_date": "2999-12-31"}]}
    assert client.put("/api/v1/promotions", json=body, headers=auth_headers(branch)).status_code == 403
    r = client.put("/api/v1/promotions", json=body, headers=auth_headers(admin))
    assert r.status_code == 200, r.text

    r = client.get("/api/v1/promotions/active", headers=auth_headers(branch))
    assert r.status_code == 200
    assert [(p["product_id"], p["promotion_name"], p["color"]) for p in r.json()] == [(a.id, "Mega Deal", "purple")]

    assert client.delete(f"/api/v1/promotions/types/{type_id}", headers=auth_headers(branch)).status_code == 403
    assert client.delete(f"/api/v1/promotions/types/{type_id}", headers=auth_headers(admin)).status_code == 204
    assert client.get("/api/v1/promotions/active", headers=auth_headers(branch)).json() == []
    assert client.delete(f"/api/v1/promotions/types/{type_id}", headers=auth_headers(admin)).status_code == 404
