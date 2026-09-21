"""
Regression tests for the fixes to BUG-03 (revocable sessions) and SEC-01 (forced password change).

Design under test
  * users.token_version is stamped into every JWT ("tv"); bumping it kills all of a user's tokens at once
    (password change/reset, deactivation, recovery redemption).
  * Logout revokes one refresh token by its "jti" (revoked_tokens table) so a shared branch/supplier login
    stays signed in on the other devices.
  * users.must_change_password blocks every endpoint except /auth/me, /auth/change-password, /auth/logout,
    /auth/refresh and the public ones, until the user picks their own password.
"""
from datetime import datetime, timedelta, timezone

import pytest

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"


def _login(client, username, password):
    return client.post(LOGIN, json={"username": username, "password": password})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------- BUG-03: revocable sessions
def test_logout_revokes_only_the_session_that_logged_out(client, make_user, make_branch):
    """Branch/supplier logins are shared by several staff and devices: logging out on one machine
    must not sign the others out."""
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-shared")
    laptop = _login(client, "qa-shared", user.plain_password).json()
    phone = _login(client, "qa-shared", user.plain_password).json()
    client.post("/api/v1/auth/logout", headers=_bearer(laptop["access_token"]), json={"refresh_token": laptop["refresh_token"]})
    assert client.post(REFRESH, json={"refresh_token": laptop["refresh_token"]}).status_code == 401
    assert client.post(REFRESH, json={"refresh_token": phone["refresh_token"]}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(phone["access_token"])).status_code == 200


def test_logout_without_a_body_still_succeeds_but_cannot_revoke(client, make_user, make_branch):
    """Old clients (no body) keep working: the call succeeds, the refresh token just isn't revoked server-side."""
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-oldclient")
    tokens = _login(client, "qa-oldclient", user.plain_password).json()
    assert client.post("/api/v1/auth/logout", headers=_bearer(tokens["access_token"])).status_code == 200
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 200


def test_logout_cannot_revoke_somebody_elses_refresh_token(client, make_user, make_branch):
    alice = make_user(role="BRANCH", branch=make_branch(), username="qa-alice")
    mallory = make_user(role="BRANCH", branch=make_branch(), username="qa-mallory")
    a = _login(client, "qa-alice", alice.plain_password).json()
    m = _login(client, "qa-mallory", mallory.plain_password).json()
    client.post("/api/v1/auth/logout", headers=_bearer(m["access_token"]), json={"refresh_token": a["refresh_token"]})
    assert client.post(REFRESH, json={"refresh_token": a["refresh_token"]}).status_code == 200


def test_logout_with_garbage_refresh_token_does_not_fail(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-garbage")
    tokens = _login(client, "qa-garbage", user.plain_password).json()
    r = client.post("/api/v1/auth/logout", headers=_bearer(tokens["access_token"]), json={"refresh_token": "not.a.jwt"})
    assert r.status_code == 200


def test_changing_password_kills_old_tokens_and_returns_fresh_ones(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-newtokens")
    old = _login(client, "qa-newtokens", user.plain_password).json()
    r = client.post("/api/v1/auth/change-password", headers=_bearer(old["access_token"]),
                    json={"current_password": user.plain_password, "new_password": "BrandNewPass1!"})
    assert r.status_code == 200
    fresh = r.json()
    assert client.get("/api/v1/auth/me", headers=_bearer(old["access_token"])).status_code == 401  # access token dead too
    assert client.get("/api/v1/auth/me", headers=_bearer(fresh["access_token"])).status_code == 200
    assert client.post(REFRESH, json={"refresh_token": fresh["refresh_token"]}).status_code == 200
    assert _login(client, "qa-newtokens", "BrandNewPass1!").status_code == 200


def test_admin_reset_also_kills_the_victims_access_token(client, make_user, make_branch, auth_headers):
    admin = make_user(role="ADMIN", username="qa-admin2")
    victim = make_user(role="BRANCH", branch=make_branch(), username="qa-victim2")
    stolen = _login(client, "qa-victim2", victim.plain_password).json()
    assert client.post(f"/api/v1/users/{victim.id}/reset-password", headers=auth_headers(admin)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(stolen["access_token"])).status_code == 401


def test_reactivating_a_user_does_not_resurrect_old_sessions(client, make_user, make_branch, auth_headers):
    admin = make_user(role="ADMIN", username="qa-admin3")
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-react")
    old = _login(client, "qa-react", user.plain_password).json()
    assert client.post(f"/api/v1/users/{user.id}/deactivate", headers=auth_headers(admin)).status_code == 200
    assert client.post(f"/api/v1/users/{user.id}/activate", headers=auth_headers(admin)).status_code == 200
    assert client.post(REFRESH, json={"refresh_token": old["refresh_token"]}).status_code == 401
    assert client.get("/api/v1/auth/me", headers=_bearer(old["access_token"])).status_code == 401


def test_recovery_token_redeem_ends_existing_sessions(client, make_user, db_session):
    from app.services import auth_service

    make_user(role="ADMIN", username="qa-recover-sessions")
    tokens = _login(client, "qa-recover-sessions", "TestPass123!").json()
    raw = auth_service.create_recovery_token(db_session, "qa-recover-sessions")
    assert client.post("/api/v1/auth/redeem-recovery-token", json={"token": raw, "new_password": "Recovered-Pass1"}).status_code == 200
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_tokens_issued_before_versioning_still_work(client, make_user, make_branch):
    """Deploying token versioning must not sign everybody out: a token with no 'tv'/'jti' claim counts as version 0."""
    from jose import jwt

    from app.core.config import settings

    user = make_user(role="BRANCH", branch=make_branch(), username="qa-legacy")
    now = datetime.now(timezone.utc)
    legacy = jwt.encode({"sub": str(user.id), "type": "access", "iat": now, "exp": now + timedelta(minutes=5)},
                        settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    assert client.get("/api/v1/auth/me", headers=_bearer(legacy)).status_code == 200


def test_token_with_a_stale_version_is_rejected_on_every_route(client, make_user, make_branch, db_session):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-stale")
    tokens = _login(client, "qa-stale", user.plain_password).json()
    user.token_version += 1
    db_session.commit()
    assert client.get("/api/v1/orders/window", headers=_bearer(tokens["access_token"])).status_code == 401
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_revoked_token_rows_are_purged_once_they_would_have_expired(client, make_user, make_branch, db_session):
    from app.models.revoked_token import RevokedToken

    user = make_user(role="BRANCH", branch=make_branch(), username="qa-purge")
    db_session.add(RevokedToken(jti="expired-one", user_id=user.id, expires_at=datetime.now(timezone.utc) - timedelta(days=1)))
    db_session.commit()
    tokens = _login(client, "qa-purge", user.plain_password).json()
    client.post("/api/v1/auth/logout", headers=_bearer(tokens["access_token"]), json={"refresh_token": tokens["refresh_token"]})
    assert db_session.get(RevokedToken, "expired-one") is None
    assert db_session.query(RevokedToken).count() == 1  # only the one just revoked


# ------------------------------------------------- SEC-01: forced password change
def _pending_user(make_user, make_branch, username):
    return make_user(role="BRANCH", branch=make_branch(), username=username, must_change_password=True)


def test_login_reports_that_a_password_change_is_required(client, make_user, make_branch):
    user = _pending_user(make_user, make_branch, "qa-pending")
    body = _login(client, "qa-pending", user.plain_password).json()
    assert body["must_change_password"] is True
    assert client.get("/api/v1/auth/me", headers=_bearer(body["access_token"])).json()["must_change_password"] is True


def test_pending_user_is_blocked_everywhere_except_the_way_out(client, make_user, make_branch):
    user = _pending_user(make_user, make_branch, "qa-blocked")
    tok = _login(client, "qa-blocked", user.plain_password).json()["access_token"]
    for path in ("/api/v1/orders/window", "/api/v1/products", "/api/v1/orders", "/api/v1/orders/mine/today",
                 "/api/v1/messages/mine", "/api/v1/orders/stock-in-hand"):
        r = client.get(path, headers=_bearer(tok))
        assert r.status_code == 403, f"{path} -> {r.status_code}"
        assert "change your password" in r.json()["detail"].lower()
    # ...but the endpoints needed to resolve it, plus the public ones, work
    assert client.get("/api/v1/auth/me", headers=_bearer(tok)).status_code == 200
    assert client.get("/api/v1/settings").status_code == 200
    assert client.post("/api/v1/auth/logout", headers=_bearer(tok)).status_code == 200


def test_pending_admin_cannot_use_admin_endpoints(client, make_user):
    admin = make_user(role="ADMIN", username="qa-pending-admin", must_change_password=True)
    tok = _login(client, "qa-pending-admin", admin.plain_password).json()["access_token"]
    assert client.get("/api/v1/users", headers=_bearer(tok)).status_code == 403


def test_pending_user_can_refresh_their_session(client, make_user, make_branch):
    user = _pending_user(make_user, make_branch, "qa-pending-refresh")
    tokens = _login(client, "qa-pending-refresh", user.plain_password).json()
    r = client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200 and r.json()["must_change_password"] is True


def test_changing_the_password_lifts_the_block_immediately(client, make_user, make_branch):
    user = _pending_user(make_user, make_branch, "qa-lift")
    tok = _login(client, "qa-lift", user.plain_password).json()["access_token"]
    r = client.post("/api/v1/auth/change-password", headers=_bearer(tok),
                    json={"current_password": user.plain_password, "new_password": "My-Own-Secret-9"})
    assert r.status_code == 200
    fresh = r.json()["access_token"]
    assert client.get("/api/v1/orders/window", headers=_bearer(fresh)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=_bearer(fresh)).json()["must_change_password"] is False
    assert _login(client, "qa-lift", "My-Own-Secret-9").json()["must_change_password"] is False


@pytest.mark.parametrize("new_password,why", [
    ("TestPass123!", "same as current"),
    ("ChangeMe123!", "the seeded default"),
    ("changeme123!", "the seeded default, different case"),
    ("qa-rules", "equals the username"),
    ("short", "too short"),
])
def test_forced_change_rejects_weak_or_unchanged_passwords(client, make_user, make_branch, new_password, why):
    user = _pending_user(make_user, make_branch, "qa-rules")
    tok = _login(client, "qa-rules", user.plain_password).json()["access_token"]
    r = client.post("/api/v1/auth/change-password", headers=_bearer(tok),
                    json={"current_password": user.plain_password, "new_password": new_password})
    assert r.status_code == 422, why
    assert client.get("/api/v1/orders/window", headers=_bearer(tok)).status_code == 403  # still pending


def test_admin_issued_passwords_are_temporary(client, make_user, make_branch, make_supplier, auth_headers, db_session):
    from app.models.user import User

    admin = make_user(role="ADMIN", username="qa-admin4")
    branch = make_branch()
    r = client.post("/api/v1/users", headers=auth_headers(admin), json={"role": "BRANCH", "branch_id": branch.id})
    assert r.status_code == 200
    created = db_session.get(User, r.json()["id"])
    assert created.must_change_password is True
    assert _login(client, r.json()["username"], r.json()["temporary_password"]).json()["must_change_password"] is True

    victim = make_user(role="SUPPLIER", supplier=make_supplier(), username="qa-victim4")
    assert client.post(f"/api/v1/users/{victim.id}/reset-password", headers=auth_headers(admin)).status_code == 200
    db_session.refresh(victim)
    assert victim.must_change_password is True


def test_admin_sets_someone_elses_password_they_must_change_it_but_own_password_is_theirs(
    client, make_user, make_branch, auth_headers, db_session
):
    admin = make_user(role="ADMIN", username="qa-admin5")
    other = make_user(role="BRANCH", branch=make_branch(), username="qa-other")
    assert client.patch(f"/api/v1/users/{other.id}", headers=auth_headers(admin), json={"password": "Chosen-By-Admin-1"}).status_code == 200
    db_session.refresh(other)
    assert other.must_change_password is True

    assert client.patch(f"/api/v1/users/{admin.id}", headers=auth_headers(admin), json={"password": "Admin-Own-Pass-1"}).status_code == 200
    db_session.refresh(admin)
    assert admin.must_change_password is False


def test_recovery_token_clears_the_flag_because_the_user_chose_the_password(client, make_user, db_session):
    from app.services import auth_service

    make_user(role="ADMIN", username="qa-recover-flag", must_change_password=True)
    raw = auth_service.create_recovery_token(db_session, "qa-recover-flag")
    assert client.post("/api/v1/auth/redeem-recovery-token", json={"token": raw, "new_password": "Recovered-Pass1"}).status_code == 200
    assert _login(client, "qa-recover-flag", "Recovered-Pass1").json()["must_change_password"] is False


def test_seed_users_flags_new_accounts_by_default(db_session, roles):
    from scripts import seed_users

    forced = seed_users.create_user_if_missing(db_session, "seed-forced", role=roles["BRANCH"])
    relaxed = seed_users.create_user_if_missing(db_session, "seed-relaxed", role=roles["BRANCH"], force_change=False)
    assert forced.must_change_password is True
    assert relaxed.must_change_password is False


def test_migration_flags_only_the_accounts_still_on_the_seeded_password(db_session, make_user, make_branch, monkeypatch):
    """Deploying migration 0018 is what forces the change on production: accounts still using
    'ChangeMe123!' are flagged, accounts that already chose their own password are left alone."""
    import importlib.util
    from pathlib import Path

    from app.models.user import User

    default = make_user(role="BRANCH", branch=make_branch(), username="mig-default", password="ChangeMe123!")
    changed = make_user(role="BRANCH", branch=make_branch(), username="mig-changed", password="Something-Else-77")
    garbage = make_user(role="BRANCH", branch=make_branch(), username="mig-garbage", password="x")
    garbage.password_hash = "not-a-hash"
    db_session.commit()

    path = Path(__file__).resolve().parents[2] / "backend" / "alembic" / "versions" / "0018_session_revocation_and_forced_password_change.py"
    spec = importlib.util.spec_from_file_location("mig0018", path)
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)

    class _Op:
        @staticmethod
        def get_bind():
            return db_session.connection()

    monkeypatch.setattr(mig, "op", _Op)
    mig._flag_accounts_still_using_a_known_default()
    db_session.expire_all()
    assert db_session.get(User, default.id).must_change_password is True
    assert db_session.get(User, changed.id).must_change_password is False
    assert db_session.get(User, garbage.id).must_change_password is True  # unreadable hash -> force a reset
