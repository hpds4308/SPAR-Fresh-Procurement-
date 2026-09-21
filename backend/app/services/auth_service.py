import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import UnauthorizedError, ValidationFailedError, NotFoundError
from app.core.security import (
    verify_password,
    hash_password,
    hash_recovery_token,
    create_access_token,
    create_refresh_token,
    decode_token_claims,
    get_user_roles,
)
from app.core.audit import write_audit_log
from app.models.password_reset_token import PasswordResetToken
from app.models.revoked_token import RevokedToken
from app.models.user import User

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
RECOVERY_TOKEN_LIFETIME_MINUTES = 30

# Passwords nobody may choose as their "new" password: the value the seed script hands to every account.
FORBIDDEN_NEW_PASSWORDS = {"changeme123!"}

# Primary role each user is routed to on login. Admin dashboard also serves
# users who hold multiple roles (not expected in the initial rollout).
ROLE_REDIRECTS = {
    "ADMIN": "/admin",
    "BRANCH": "/branch",
    "SUPPLIER": "/supplier",
}


def authenticate(
    db: Session, username: str, password: str, ip_address: str | None = None
) -> tuple[str, str, str, str, bool]:
    """Returns (access_token, refresh_token, role, redirect_to, must_change_password)."""
    user = db.query(User).filter(User.username == username).first()

    if user and user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise UnauthorizedError("Account temporarily locked due to repeated failed logins. Try again later.")

    if not user or not verify_password(password, user.password_hash):
        if user:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
        raise UnauthorizedError("Incorrect username or password.")

    if not user.is_active:
        raise UnauthorizedError("This account has been deactivated.")

    roles = get_user_roles(db, user.id)
    if not roles:
        raise UnauthorizedError("This account has no assigned role. Contact an administrator.")
    primary_role = roles[0]

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    write_audit_log(
        db,
        user_id=user.id,
        role=primary_role,
        action="LOGIN",
        entity_type="user",
        entity_id=user.id,
        ip_address=ip_address,
    )

    access_token = create_access_token(user.id, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)
    redirect_to = ROLE_REDIRECTS.get(primary_role, "/")
    return access_token, refresh_token, primary_role, redirect_to, user.must_change_password


def refresh_session(db: Session, raw_refresh_token: str) -> tuple[str, str, str, str, bool]:
    """
    Issues a new access token for a still-valid refresh token. Refuses it if the account was
    deactivated, if its token_version moved on (password change/reset, deactivation, recovery), or if
    this specific token was revoked at logout. The refresh token itself is returned unchanged:
    rotating it would sign users out whenever two tabs refresh at the same moment.
    """
    claims = decode_token_claims(raw_refresh_token, expected_type="refresh")
    user = db.get(User, claims.user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("Account is inactive or does not exist.")
    if user.token_version != claims.token_version:
        raise UnauthorizedError("Your session has ended. Please sign in again.")
    if claims.jti and db.get(RevokedToken, claims.jti) is not None:
        raise UnauthorizedError("Your session has ended. Please sign in again.")
    roles = get_user_roles(db, user.id)
    primary_role = roles[0] if roles else ""
    return (
        create_access_token(user.id, user.token_version),
        raw_refresh_token,
        primary_role,
        ROLE_REDIRECTS.get(primary_role, "/"),
        user.must_change_password,
    )


def revoke_refresh_token(db: Session, user: User, raw_refresh_token: str | None) -> bool:
    """
    Logout: kill this one refresh token (other sessions of a shared branch/supplier login keep
    working). Silently ignores a missing/garbage/foreign token - logout must never fail. Also purges
    deny-list rows whose tokens have expired by themselves. Returns True if a token was revoked.
    """
    now = datetime.now(timezone.utc)
    db.query(RevokedToken).filter(RevokedToken.expires_at < now).delete()
    revoked = False
    if raw_refresh_token:
        try:
            claims = decode_token_claims(raw_refresh_token, expected_type="refresh")
        except UnauthorizedError:
            claims = None
        if claims and claims.jti and claims.user_id == user.id and db.get(RevokedToken, claims.jti) is None:
            db.add(RevokedToken(jti=claims.jti, user_id=user.id, expires_at=claims.expires_at))
            revoked = True
    try:
        db.commit()
    except IntegrityError:
        # Two logouts of the very same token raced past the check above; the other one won, which is the
        # outcome we wanted anyway. Logout must never fail.
        db.rollback()
    return revoked


def change_password(db: Session, user: User, current_password: str, new_password: str) -> tuple[str, str]:
    """
    Changes the caller's own password, clears must_change_password, and revokes every token issued
    before now (token_version bump). Returns a fresh (access, refresh) pair so the caller's own session
    carries on without a second sign-in.
    """
    if not verify_password(current_password, user.password_hash):
        raise ValidationFailedError("Current password is incorrect.")
    if new_password == current_password:
        raise ValidationFailedError("Choose a password different from your current one.")
    if new_password.strip().lower() in FORBIDDEN_NEW_PASSWORDS or new_password.strip().lower() == user.username.lower():
        raise ValidationFailedError("That password is too easy to guess. Choose a different one.")
    user.password_hash = hash_password(new_password)
    user.token_version += 1
    user.must_change_password = False
    db.commit()
    write_audit_log(
        db,
        user_id=user.id,
        role=None,
        action="PASSWORD_CHANGED",
        entity_type="user",
        entity_id=user.id,
    )
    return create_access_token(user.id, user.token_version), create_refresh_token(user.id, user.token_version)


def create_recovery_token(db: Session, username: str) -> str:
    """
    Generates a one-time break-glass recovery token for one account and
    returns the RAW token — the only moment it ever exists in plain form;
    only its hash is stored (see PasswordResetToken). Only ever called from
    scripts/generate_recovery_token.py by whoever has direct server access;
    there is no API path that reaches this, since the whole point is
    recovering an account that can't authenticate at all.

    Invalidates any earlier unused token for this user first, so at most
    one is ever valid at a time — generating a new one supersedes the last.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise NotFoundError(f"No account with username '{username}'.")

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None)
    ).delete()

    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_recovery_token(raw_token),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=RECOVERY_TOKEN_LIFETIME_MINUTES),
        )
    )
    db.commit()
    return raw_token


def redeem_recovery_token(db: Session, raw_token: str, new_password: str) -> None:
    """
    Sets a new password using a break-glass recovery token instead of the
    current one — the only account-recovery path available when someone
    genuinely cannot log in at all (see PasswordResetToken). Also clears
    any failed-login lockout, since that's often exactly why they ended up
    needing this in the first place.
    """
    row = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.token_hash == hash_recovery_token(raw_token),
            PasswordResetToken.used_at.is_(None),
        )
        .first()
    )
    # Same message whether the token is wrong, already used, or expired —
    # never reveal which, so a guessed/stale token can't be narrowed down.
    if not row or row.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("This recovery link is invalid or has expired.")

    user = db.get(User, row.user_id)
    if not user:
        raise UnauthorizedError("This recovery link is invalid or has expired.")

    user.password_hash = hash_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.token_version += 1  # whoever held a session on the old password loses it
    user.must_change_password = False  # the user picked this password themselves
    row.used_at = datetime.now(timezone.utc)
    db.commit()

    write_audit_log(
        db,
        user_id=user.id,
        role=None,
        action="PASSWORD_RESET_VIA_RECOVERY_TOKEN",
        entity_type="user",
        entity_id=user.id,
        description="Password reset using a server-generated recovery token — account was otherwise locked out.",
    )
