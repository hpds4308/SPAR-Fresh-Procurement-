"""
DB-backed tests for suppliers' final price lists — final_price_service.py.
"""
from datetime import timedelta

import pytest

from app.core.errors import NotFoundError, ValidationFailedError
from app.services import final_price_service as fp, price_approval_service as svc
from tests.test_price_approval_db import SIGNATURE, _adjust_all, _decide, _respond, _send, ctx  # noqa: F401


def _after_cutoff(db_session, ctx, monkeypatch, minutes=1):
    closes = svc.expires_at(ctx["delivery"], svc.approval_cutoff(db_session))
    monkeypatch.setattr(svc, "_now", lambda: closes + timedelta(minutes=minutes))


def _sign(db_session, ctx):
    return fp.set_signature(db_session, ctx["admin"], name="D. Pathirage", title="Commercial Manager", signature_image=SIGNATURE)


def test_not_final_before_the_cutoff(db_session, ctx, monkeypatch):
    _after_cutoff(db_session, ctx, monkeypatch, minutes=-1)
    assert fp.final_dates(db_session, ctx["supplier_user"])["dates"] == []
    assert fp.final_dates(db_session, ctx["supplier_user"])["next_delivery_date"] == ctx["delivery"]
    with pytest.raises(ValidationFailedError):
        fp.build_list(db_session, ctx["supplier_user"], ctx["delivery"])


def test_final_prices_follow_each_items_answer(db_session, ctx, monkeypatch):
    _adjust_all(db_session, ctx)  # 100 -> 90, 110 -> 95
    _respond(db_session, ctx, _send(db_session, ctx), _decide(ctx, ("APPROVED", None), ("REJECTED", 105)))
    _after_cutoff(db_session, ctx, monkeypatch)

    assert fp.final_dates(db_session, ctx["supplier_user"])["dates"] == [ctx["delivery"]]
    data = fp.build_list(db_session, ctx["supplier_user"], ctx["delivery"])
    by_product = {l["product_id"]: l for l in data["lines"]}
    first, second = (by_product[r.product_id] for r in ctx["rows"])
    assert (first["final_price"], first["basis"], first["adjusted_price"]) == (90.0, fp.BASIS_APPROVED, 90.0)
    assert (second["final_price"], second["basis"]) == (105.0, fp.BASIS_COUNTER)
    assert [s["signature_image"] for s in data["supplier_signatures"]] == [SIGNATURE]


def test_unanswered_and_draft_adjustments_use_own_price(db_session, ctx, monkeypatch):
    _adjust_all(db_session, ctx)
    _send(db_session, ctx)  # never answered
    _after_cutoff(db_session, ctx, monkeypatch)
    data = fp.build_list(db_session, ctx["supplier_user"], ctx["delivery"])
    assert {l["final_price"] for l in data["lines"]} == {100.0, 110.0}
    assert {l["basis"] for l in data["lines"]} == {fp.BASIS_EXPIRED}
    assert data["supplier_signatures"] == []


def test_downloads_need_spar_signature(db_session, ctx, monkeypatch):
    _after_cutoff(db_session, ctx, monkeypatch)
    data = fp.build_list(db_session, ctx["supplier_user"], ctx["delivery"])
    with pytest.raises(ValidationFailedError):
        fp.build_pdf(data)

    _sign(db_session, ctx)
    data = fp.build_list(db_session, ctx["supplier_user"], ctx["delivery"])
    assert data["spar_signature"]["signatory_name"] == "D. Pathirage"
    assert fp.build_pdf(data).startswith(b"%PDF-")
    assert fp.build_excel(data)[:2] == b"PK"


def test_other_supplier_sees_nothing(db_session, ctx, monkeypatch, make_supplier, make_user):
    other = make_user(role="SUPPLIER", supplier=make_supplier())
    _after_cutoff(db_session, ctx, monkeypatch)
    assert fp.final_dates(db_session, other)["dates"] == []
    with pytest.raises(NotFoundError):
        fp.build_list(db_session, other, ctx["delivery"])


def test_endpoints(client, db_session, ctx, monkeypatch, auth_headers):
    supplier_h = auth_headers(ctx["supplier_user"])
    admin_h = auth_headers(ctx["admin"])

    # Only Admin sets SPAR's signature; suppliers can't read or change it.
    assert client.put("/api/v1/final-prices/signature", json={"signatory_name": "X", "signature_image": SIGNATURE}, headers=supplier_h).status_code == 403
    r = client.put(
        "/api/v1/final-prices/signature",
        json={"signatory_name": "D. Pathirage", "signatory_title": "Commercial Manager", "signature_image": SIGNATURE},
        headers=admin_h,
    )
    assert r.status_code == 200, r.text
    assert client.put(
        "/api/v1/final-prices/signature", json={"signatory_name": "X", "signature_image": "data:image/png;base64,AAAA"}, headers=admin_h
    ).status_code == 422

    _after_cutoff(db_session, ctx, monkeypatch)
    dates = client.get("/api/v1/final-prices/mine/dates", headers=supplier_h).json()
    assert dates["dates"] == [ctx["delivery"].isoformat()] and dates["signature_ready"] is True
    q = f"?delivery_date={ctx['delivery'].isoformat()}"
    assert len(client.get(f"/api/v1/final-prices/mine{q}", headers=supplier_h).json()["lines"]) == 2
    pdf = client.get(f"/api/v1/final-prices/mine/pdf{q}", headers=supplier_h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    xlsx = client.get(f"/api/v1/final-prices/mine/excel{q}", headers=supplier_h)
    assert xlsx.status_code == 200 and xlsx.content[:2] == b"PK"
    assert client.get(f"/api/v1/final-prices/mine{q}", headers=admin_h).status_code == 403
