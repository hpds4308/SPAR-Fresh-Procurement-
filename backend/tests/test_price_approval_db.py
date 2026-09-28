"""
DB-backed tests for supplier approval (e-signature) of Admin's adjusted
prices — price_approval_service.py.
"""
import base64
import struct
import zlib
from datetime import date, datetime, timedelta

import pytest

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models.pricing import SupplierPrice
from app.services import master_data_service, price_approval_service as svc, pricing_service
from app.services.price_approval_service import BUSINESS_TZ


def _png_data_url(width=40, height=20) -> str:
    """A real (tiny, blank) PNG, standing in for a drawn signature."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * width for _ in range(height))
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    return "data:image/png;base64," + base64.b64encode(png).decode()


SIGNATURE = _png_data_url()
PASSWORD = "TestPass123!"


def _future_date(days=5) -> date:
    return datetime.now(BUSINESS_TZ).date() + timedelta(days=days)


@pytest.fixture()
def ctx(db_session, make_supplier, make_user, make_product):
    supplier = make_supplier()
    supplier_user = make_user(role="SUPPLIER", supplier=supplier, password=PASSWORD)
    admin = make_user(role="ADMIN")
    products = [make_product(), make_product()]
    delivery = _future_date()
    rows = []
    for i, product in enumerate(products):
        row = SupplierPrice(
            supplier_id=supplier.id,
            product_id=product.id,
            delivery_date=delivery,
            price=100 + i * 10,
            unit_code="KG",
            submitted_by=supplier_user.id,
        )
        db_session.add(row)
        rows.append(row)
    db_session.commit()
    return dict(supplier=supplier, supplier_user=supplier_user, admin=admin, rows=rows, delivery=delivery)


def _adjust_all(db_session, ctx, prices=(90, 95)):
    for row, price in zip(ctx["rows"], prices):
        pricing_service.set_adjusted_price(db_session, ctx["admin"], row.id, price)


def _send(db_session, ctx):
    return svc.send_for_approval(db_session, ctx["admin"], ctx["supplier"].id, ctx["delivery"])


def _approve(db_session, ctx, rev, **overrides):
    kwargs = dict(
        snapshot_hash=rev.snapshot_hash,
        signer_name="Nimal Perera",
        signature_image=SIGNATURE,
        password=PASSWORD,
        ip_address="203.0.113.7",
        user_agent="pytest",
    )
    kwargs.update(overrides)
    return svc.approve(db_session, ctx["supplier_user"], rev.id, **kwargs)


def _status(db_session, row):
    db_session.refresh(row)
    return svc.row_statuses(db_session, [row])[row.id][0]


def test_send_groups_all_adjustments_into_one_sheet(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)

    assert rev.status == svc.PENDING
    assert len(rev.items) == 2
    assert {i["adjusted_price"] for i in rev.items} == {90.0, 95.0}
    assert rev.snapshot_hash == svc.compute_snapshot_hash(rev.supplier_id, rev.delivery_date, rev.items)
    for row in ctx["rows"]:
        db_session.refresh(row)
        assert row.revision_id == rev.id
        assert row.sent_to_supplier_at is not None
    assert svc.supplier_pending_count(db_session, ctx["supplier_user"]) == 1


def test_send_with_nothing_adjusted_is_refused(db_session, ctx):
    with pytest.raises(ValidationFailedError):
        _send(db_session, ctx)


def test_approve_records_signature_evidence(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _approve(db_session, ctx, _send(db_session, ctx))

    assert rev.status == svc.APPROVED
    assert rev.signer_name == "Nimal Perera"
    assert rev.signature_image == SIGNATURE
    assert rev.signer_ip == "203.0.113.7"
    assert rev.responded_by == ctx["supplier_user"].id
    assert _status(db_session, ctx["rows"][0]) == svc.APPROVED
    assert svc.supplier_pending_count(db_session, ctx["supplier_user"]) == 0


def test_wrong_password_is_refused_and_counts_towards_lockout(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    for _ in range(svc.MAX_FAILED_ATTEMPTS):
        with pytest.raises(ValidationFailedError):
            _approve(db_session, ctx, rev, password="wrong")
    with pytest.raises(PermissionDeniedError):
        _approve(db_session, ctx, rev)
    db_session.refresh(rev)
    assert rev.status == svc.PENDING


@pytest.mark.parametrize("image", ["", "data:image/png;base64,not-base64!!", "data:image/jpeg;base64,AAAA"])
def test_missing_or_invalid_signature_is_refused(db_session, ctx, image):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    with pytest.raises(ValidationFailedError):
        _approve(db_session, ctx, rev, signature_image=image)


def test_stale_hash_is_refused(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    with pytest.raises(ValidationFailedError):
        _approve(db_session, ctx, rev, snapshot_hash="0" * 64)


def test_other_supplier_cannot_see_or_sign(db_session, ctx, make_supplier, make_user):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    outsider = make_user(role="SUPPLIER", supplier=make_supplier(), password=PASSWORD)
    with pytest.raises(NotFoundError):
        svc.get_own_revision(db_session, outsider, rev.id)
    with pytest.raises(NotFoundError):
        svc.approve(
            db_session, outsider, rev.id, snapshot_hash=rev.snapshot_hash, signer_name="X Y",
            signature_image=SIGNATURE, password=PASSWORD, ip_address=None, user_agent=None,
        )


def test_editing_after_approval_voids_whole_sheet(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _approve(db_session, ctx, _send(db_session, ctx))

    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["rows"][0].id, 88)

    db_session.refresh(rev)
    assert rev.status == svc.VOIDED
    assert rev.signature_image == SIGNATURE  # evidence kept
    assert _status(db_session, ctx["rows"][0]) == svc.DRAFT
    assert _status(db_session, ctx["rows"][1]) == svc.DRAFT  # the untouched item goes back too
    assert ctx["rows"][1].sent_to_supplier_at is None


def test_resaving_same_value_does_not_void(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _approve(db_session, ctx, _send(db_session, ctx))
    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["rows"][0].id, 90)
    db_session.refresh(rev)
    assert rev.status == svc.APPROVED


def test_editing_pending_sheet_then_resending_makes_new_sheet(db_session, ctx):
    _adjust_all(db_session, ctx)
    first = _send(db_session, ctx)
    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["rows"][0].id, 85)
    db_session.refresh(first)
    assert first.status == svc.VOIDED

    second = _send(db_session, ctx)
    assert second.id != first.id
    assert {i["adjusted_price"] for i in second.items} == {85.0, 95.0}
    # The supplier's copy of the old sheet can no longer be signed.
    with pytest.raises(ValidationFailedError):
        _approve(db_session, ctx, first)


def test_resend_folds_pending_sheet_into_new_one(db_session, ctx):
    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["rows"][0].id, 90)
    first = _send(db_session, ctx)
    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["rows"][1].id, 95)
    second = _send(db_session, ctx)

    db_session.refresh(first)
    assert first.status == svc.VOIDED
    assert len(second.items) == 2


def test_approved_items_are_not_resent(db_session, ctx):
    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["rows"][0].id, 90)
    first = _approve(db_session, ctx, _send(db_session, ctx))
    pricing_service.set_adjusted_price(db_session, ctx["admin"], ctx["rows"][1].id, 95)
    second = _send(db_session, ctx)

    db_session.refresh(first)
    assert first.status == svc.APPROVED
    assert [i["supplier_price_id"] for i in second.items] == [ctx["rows"][1].id]


def test_reject_then_resend(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    rejected = svc.reject(db_session, ctx["supplier_user"], rev.id, snapshot_hash=rev.snapshot_hash, reason="Too low")
    assert rejected.status == svc.REJECTED
    assert rejected.rejection_reason == "Too low"
    assert _status(db_session, ctx["rows"][0]) == svc.REJECTED
    assert svc.admin_attention_count(db_session) == 1

    # Admin can resend as-is (e.g. after a phone call) — a new sheet.
    again = _send(db_session, ctx)
    assert again.status == svc.PENDING
    assert svc.admin_attention_count(db_session) == 0


def test_withdraw_returns_items_to_draft(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = svc.withdraw(db_session, ctx["admin"], _send(db_session, ctx).id)
    assert rev.status == svc.WITHDRAWN
    assert _status(db_session, ctx["rows"][0]) == svc.DRAFT
    with pytest.raises(ValidationFailedError):
        svc.withdraw(db_session, ctx["admin"], rev.id)


def test_pending_sheet_expires_on_delivery_date(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    assert svc.effective_status(rev, svc.expires_at(rev.delivery_date) - timedelta(minutes=1)) == svc.PENDING
    assert svc.effective_status(rev, svc.expires_at(rev.delivery_date)) == svc.EXPIRED


def test_cannot_send_for_delivery_that_has_started(db_session, ctx):
    today = datetime.now(BUSINESS_TZ).date()
    with pytest.raises(ValidationFailedError):
        svc.send_for_approval(db_session, ctx["admin"], ctx["supplier"].id, today)


def test_supplier_resubmission_voids_pending_sheet(db_session, ctx):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    svc.on_supplier_resubmitted(db_session, ctx["supplier"].id, ctx["delivery"])
    db_session.commit()
    db_session.refresh(rev)
    assert rev.status == svc.VOIDED
    assert _status(db_session, ctx["rows"][0]) == svc.DRAFT


def test_master_data_uses_adjusted_price_only_once_approved(db_session, ctx):
    _adjust_all(db_session, ctx)
    key = (ctx["supplier"].id, ctx["rows"][0].product_id)

    latest, _ = master_data_service._latest_prices(db_session)
    assert latest[key] == 100.0  # draft — supplier's own price applies

    rev = _send(db_session, ctx)
    latest, _ = master_data_service._latest_prices(db_session)
    assert latest[key] == 100.0  # waiting for signature

    _approve(db_session, ctx, rev)
    latest, submitted = master_data_service._latest_prices(db_session)
    assert latest[key] == 90.0
    assert submitted[key][0] == 100.0  # Cost Price still uses the submitted price


def test_approve_endpoint_end_to_end(client, db_session, ctx, auth_headers):
    _adjust_all(db_session, ctx)
    admin_h = auth_headers(ctx["admin"])
    supplier_h = auth_headers(ctx["supplier_user"])

    resp = client.post(
        "/api/v1/price-approvals/admin",
        headers=admin_h,
        json={"supplier_id": ctx["supplier"].id, "delivery_date": ctx["delivery"].isoformat()},
    )
    assert resp.status_code == 200, resp.text
    sheet = resp.json()

    resp = client.get("/api/v1/price-approvals/mine/pending-count", headers=supplier_h)
    assert resp.json() == {"count": 1}

    resp = client.get(f"/api/v1/pricing/mine?delivery_date={ctx['delivery'].isoformat()}", headers=supplier_h)
    assert {r["approval_status"] for r in resp.json()} == {"PENDING"}

    resp = client.post(
        f"/api/v1/price-approvals/mine/{sheet['id']}/approve",
        headers={**supplier_h, "X-Forwarded-For": "198.51.100.4"},
        json={
            "snapshot_hash": sheet["snapshot_hash"],
            "signer_name": "  Nimal   Perera ",
            "signature_image": SIGNATURE,
            "password": PASSWORD,
            "agreed": True,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "APPROVED"
    assert body["signer_name"] == "Nimal Perera"
    assert body["signer_ip"] == "198.51.100.4"

    # Admin can't act on supplier routes and vice versa.
    assert client.get("/api/v1/price-approvals/mine", headers=admin_h).status_code == 403
    assert client.get("/api/v1/price-approvals/admin", headers=supplier_h).status_code == 403


def test_approve_requires_agreement_tick(client, db_session, ctx, auth_headers):
    _adjust_all(db_session, ctx)
    rev = _send(db_session, ctx)
    resp = client.post(
        f"/api/v1/price-approvals/mine/{rev.id}/approve",
        headers=auth_headers(ctx["supplier_user"]),
        json={
            "snapshot_hash": rev.snapshot_hash,
            "signer_name": "Nimal Perera",
            "signature_image": SIGNATURE,
            "password": PASSWORD,
            "agreed": False,
        },
    )
    assert resp.status_code == 422
