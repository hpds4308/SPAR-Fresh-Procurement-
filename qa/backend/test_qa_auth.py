"""
QA: authentication & session handling.

Evidence for: BUG-01 (lockout never resets), BUG-02 (case/space-sensitive
username), BUG-03 (refresh tokens survive logout / password reset),
BUG-04 (admin can deactivate own account), BUG-05 (username enumeration via
lockout message).  See qa/QA_REPORT.md.
"""
from datetime import datetime, timedelta, timezone

import pytest

LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"


def _login(client, username, password):
    return client.post(LOGIN, json={"username": username, "password": password})


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ----------------------------------------------------------------- happy paths
def test_login_success_returns_tokens_and_role_redirect(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-branch")
    r = _login(client, "qa-branch", user.plain_password)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "BRANCH" and body["redirect_to"] == "/branch"
    assert body["access_token"] and body["refresh_token"]


def test_wrong_password_is_401_with_generic_message(client, make_user, make_branch):
    make_user(role="BRANCH", branch=make_branch(), username="qa-branch")
    r = _login(client, "qa-branch", "definitely-wrong")
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect username or password."


def test_unknown_user_gets_same_message_as_wrong_password(client):
    r = _login(client, "no-such-user", "whatever123")
    assert r.status_code == 401
    assert r.json()["detail"] == "Incorrect username or password."


def test_lockout_after_five_failures_blocks_even_correct_password(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-lock")
    for _ in range(5):
        assert _login(client, "qa-lock", "bad-password").status_code == 401
    r = _login(client, "qa-lock", user.plain_password)
    assert r.status_code == 401
    assert "locked" in r.json()["detail"].lower()


def test_login_rate_limit_returns_429_after_ten_attempts_per_minute(client):
    codes = [_login(client, f"nobody{i}", "x").status_code for i in range(12)]
    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]


def test_access_token_is_rejected_where_refresh_expected_and_vice_versa(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-types")
    tokens = _login(client, "qa-types", user.plain_password).json()
    # access token used as a refresh token
    assert client.post(REFRESH, json={"refresh_token": tokens["access_token"]}).status_code == 401
    # refresh token used as a bearer token
    assert client.get("/api/v1/auth/me", headers=_bearer(tokens["refresh_token"])).status_code == 401


def test_deactivated_user_cannot_refresh(client, make_user, make_branch, db_session):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-deact")
    tokens = _login(client, "qa-deact", user.plain_password).json()
    user.is_active = False
    db_session.commit()
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401


# ------------------------------------------------------------------- confirmed bugs (BUG-03 now fixed, the rest still pinned)
@pytest.mark.xfail(strict=True, reason="BUG-01: failed_login_attempts is not reset when a lockout expires, "
                   "so ONE typo after the 15 min wait re-locks the account (auth_service.py:35-44)")
def test_bug01_single_typo_after_lockout_expiry_does_not_relock(client, make_user, make_branch, db_session):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-relock")
    for _ in range(5):
        _login(client, "qa-relock", "bad-password")
    # simulate the 15 minutes having passed
    db_session.refresh(user)
    assert user.locked_until is not None
    user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()

    assert _login(client, "qa-relock", "one-more-typo").status_code == 401
    db_session.refresh(user)
    relocked = user.locked_until is not None and user.locked_until > datetime.now(timezone.utc)
    assert not relocked, "account was immediately re-locked for another 15 minutes after a single typo"


@pytest.mark.xfail(strict=True, reason="BUG-02: username match is case- and whitespace-sensitive; phone keyboards "
                   "auto-capitalise 'br01' -> 'Br01' (auth_service.py:33, LoginPage.tsx has no autoCapitalize=none)")
@pytest.mark.parametrize("typed", ["Br01", "BR01", " br01", "br01 "])
def test_bug02_login_tolerates_case_and_surrounding_whitespace(client, make_user, make_branch, typed):
    user = make_user(role="BRANCH", branch=make_branch(), username="br01")
    assert _login(client, typed, user.plain_password).status_code == 200


def test_bug03a_refresh_token_is_unusable_after_logout(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-logout")
    tokens = _login(client, "qa-logout", user.plain_password).json()
    # FIXED (BUG-03): the SPA sends its refresh token with the logout call, so exactly that session is revoked.
    r = client.post("/api/v1/auth/logout", headers=_bearer(tokens["access_token"]), json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_bug03b_refresh_token_is_unusable_after_password_change(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-chpw")
    tokens = _login(client, "qa-chpw", user.plain_password).json()
    r = client.post("/api/v1/auth/change-password", headers=_bearer(tokens["access_token"]),
                    json={"current_password": user.plain_password, "new_password": "BrandNewPass1!"})
    assert r.status_code == 200
    assert client.post(REFRESH, json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_bug03c_refresh_token_is_unusable_after_admin_password_reset(client, make_user, make_branch, auth_headers):
    admin = make_user(role="ADMIN", username="qa-admin")
    victim = make_user(role="BRANCH", branch=make_branch(), username="qa-victim")
    stolen = _login(client, "qa-victim", victim.plain_password).json()
    r = client.post(f"/api/v1/users/{victim.id}/reset-password", headers=auth_headers(admin))
    assert r.status_code == 200
    assert client.post(REFRESH, json={"refresh_token": stolen["refresh_token"]}).status_code == 401


@pytest.mark.xfail(strict=True, reason="BUG-04: an admin can deactivate their own account; scripts/generate_recovery_token "
                   "+ redeem flow does not re-activate it, so the sole admin is permanently locked out (users.py:279-287)")
def test_bug04_admin_cannot_deactivate_own_account(client, make_user, auth_headers):
    admin = make_user(role="ADMIN", username="qa-solo-admin")
    r = client.post(f"/api/v1/users/{admin.id}/deactivate", headers=auth_headers(admin))
    assert r.status_code >= 400


@pytest.mark.xfail(strict=True, reason="BUG-05 (low): the 'locked' message is only returned for accounts that exist, so "
                   "usernames (br01..br13, sup01.., admin) can be enumerated (auth_service.py:35-36)")
def test_bug05_locked_and_nonexistent_accounts_are_indistinguishable(client, make_user, make_branch):
    make_user(role="BRANCH", branch=make_branch(), username="qa-enum")
    for _ in range(5):
        _login(client, "qa-enum", "bad-password")
    locked_msg = _login(client, "qa-enum", "bad-password").json()["detail"]
    ghost_msg = _login(client, "qa-ghost-account", "bad-password").json()["detail"]
    assert locked_msg == ghost_msg


# --------------------------------------------------------------- password policy
@pytest.mark.xfail(strict=False, reason="RISK-01: password policy is only min_length=8 (schemas/auth.py:23) - "
                   "'aaaaaaaa' and the seeded 'ChangeMe123!' style are accepted; no max length either")
def test_risk01_trivial_password_is_rejected(client, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch(), username="qa-policy")
    token = _login(client, "qa-policy", user.plain_password).json()["access_token"]
    r = client.post("/api/v1/auth/change-password", headers=_bearer(token),
                    json={"current_password": user.plain_password, "new_password": "aaaaaaaa"})
    assert r.status_code == 422


# ------------------------------------------------------- break-glass recovery token
def test_recovery_token_happy_path_resets_password_and_clears_lockout(client, make_user, make_branch, db_session):
    from app.services import auth_service

    user = make_user(role="ADMIN", username="qa-recover")
    for _ in range(5):
        _login(client, "qa-recover", "bad-password")
    raw = auth_service.create_recovery_token(db_session, "qa-recover")
    r = client.post("/api/v1/auth/redeem-recovery-token", json={"token": raw, "new_password": "Recovered-Pass1"})
    assert r.status_code == 200
    assert _login(client, "qa-recover", "Recovered-Pass1").status_code == 200  # lockout cleared too


def test_recovery_token_is_single_use(client, make_user, db_session):
    from app.services import auth_service

    make_user(role="ADMIN", username="qa-once")
    raw = auth_service.create_recovery_token(db_session, "qa-once")
    body = {"token": raw, "new_password": "Recovered-Pass1"}
    assert client.post("/api/v1/auth/redeem-recovery-token", json=body).status_code == 200
    r2 = client.post("/api/v1/auth/redeem-recovery-token", json=body)
    assert r2.status_code == 401


def test_recovery_token_expired_and_wrong_look_identical(client, make_user, db_session):
    from app.models.password_reset_token import PasswordResetToken
    from app.services import auth_service

    make_user(role="ADMIN", username="qa-expired")
    raw = auth_service.create_recovery_token(db_session, "qa-expired")
    row = db_session.query(PasswordResetToken).first()
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db_session.commit()
    expired = client.post("/api/v1/auth/redeem-recovery-token", json={"token": raw, "new_password": "Recovered-Pass1"})
    wrong = client.post("/api/v1/auth/redeem-recovery-token", json={"token": "not-a-real-token", "new_password": "Recovered-Pass1"})
    assert expired.status_code == wrong.status_code == 401
    assert expired.json() == wrong.json()


def test_new_recovery_token_supersedes_the_previous_one(client, make_user, db_session):
    from app.services import auth_service

    make_user(role="ADMIN", username="qa-super")
    first = auth_service.create_recovery_token(db_session, "qa-super")
    second = auth_service.create_recovery_token(db_session, "qa-super")
    assert client.post("/api/v1/auth/redeem-recovery-token", json={"token": first, "new_password": "Recovered-Pass1"}).status_code == 401
    assert client.post("/api/v1/auth/redeem-recovery-token", json={"token": second, "new_password": "Recovered-Pass1"}).status_code == 200


@pytest.mark.xfail(strict=False, reason="BUG-04b: redeeming a recovery token does not re-activate a deactivated account, so it cannot "
                   "rescue a self-deactivated admin (auth_service.py:122-151 never sets is_active)")
def test_bug04b_recovery_token_can_rescue_a_deactivated_admin(client, make_user, db_session):
    from app.services import auth_service

    admin = make_user(role="ADMIN", username="qa-rescue", is_active=False)
    raw = auth_service.create_recovery_token(db_session, "qa-rescue")
    assert client.post("/api/v1/auth/redeem-recovery-token", json={"token": raw, "new_password": "Recovered-Pass1"}).status_code == 200
    assert _login(client, "qa-rescue", "Recovered-Pass1").status_code == 200
