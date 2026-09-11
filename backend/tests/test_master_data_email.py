"""
"Send to Master Data" wiring: the recipient address comes from the
Admin-editable system setting, and both "no recipient set" and "SMTP not
configured" surface as clean 422s rather than 500s. Actual SMTP delivery
isn't exercised here — there's no mail server in the test environment.
"""
import pytest

from app.services import settings_service


@pytest.fixture()
def admin(make_user):
    return make_user(role="ADMIN")


@pytest.fixture(autouse=True)
def _no_smtp(monkeypatch):
    # A dev running the suite with a real backend/.env shouldn't have these
    # tests actually try to send mail — pin SMTP off for the whole module.
    from app.core.config import settings

    monkeypatch.setattr(settings, "SMTP_HOST", "")


def test_send_email_without_recipient_is_rejected(client, auth_headers, admin):
    resp = client.post("/api/v1/master-data/send-email", headers=auth_headers(admin))
    assert resp.status_code == 422
    assert "Admin → Settings" in resp.json()["detail"]


def test_send_email_with_recipient_but_no_smtp_is_rejected(client, auth_headers, admin, db_session):
    settings_service.set_setting(
        db_session, admin, settings_service.MASTER_DATA_EMAIL, "master.data@example.com"
    )
    resp = client.post("/api/v1/master-data/send-email", headers=auth_headers(admin))
    # Gets past the recipient check, then fails on SMTP not being configured.
    assert resp.status_code == 422
    assert "SMTP" in resp.json()["detail"]


def test_recipient_setting_roundtrips_and_rejects_junk(client, auth_headers, admin):
    get_before = client.get("/api/v1/settings/master-data-email", headers=auth_headers(admin))
    assert get_before.status_code == 200
    assert get_before.json() == {"master_data_email": ""}

    bad = client.put(
        "/api/v1/settings/master-data-email",
        headers=auth_headers(admin),
        json={"value": "not-an-email"},
    )
    assert bad.status_code == 422

    ok = client.put(
        "/api/v1/settings/master-data-email",
        headers=auth_headers(admin),
        json={"value": "master.data@example.com"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"master_data_email": "master.data@example.com"}


def test_recipient_setting_is_not_in_public_settings_payload(client):
    resp = client.get("/api/v1/settings")
    assert resp.status_code == 200
    assert "master_data_email" not in resp.json()


def test_recipient_setting_requires_admin(client, auth_headers, make_user, make_branch):
    branch_user = make_user(role="BRANCH", branch=make_branch())
    resp = client.get("/api/v1/settings/master-data-email", headers=auth_headers(branch_user))
    assert resp.status_code == 403
