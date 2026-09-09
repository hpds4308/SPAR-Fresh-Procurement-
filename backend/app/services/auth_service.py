import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.errors import UnauthorizedError, ValidationFailedError, NotFoundError
from app.core.security import (
    verify_password,
    hash_password,
    hash_recovery_token,
    create_access_token,
    create_refresh_token,
    get_user_roles,
)
from app.core.audit import write_audit_log
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15
RECOVERY_TOKEN_LIFETIME_MINUTES = 30

# Primary role each user is routed to on login. Admin dashboard also serves
# users who hold multiple roles (not expected in the initial rollout).
ROLE_REDIRECTS = {
    "ADMIN": "/admin",
    "BRANCH": "/branch",
    "SUPPLIER": "/supplier",
}


def authenticate(db: Session, username: str, password: str, ip_address: str | None = None) -> tuple[str, str, str, str]:
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

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    redirect_to = ROLE_REDIRECTS.get(primary_role, "/")
    return access_token, refresh_token, primary_role, redirect_to


def change_password(db: Session, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise ValidationFailedError("Current password is incorrect.")
    user.password_hash = hash_password(new_password)
    db.commit()
    write_audit_log(
        db,
        user_id=user.id,
        role=None,
        action="PASSWORD_CHANGED",
        entity_type="user",
        entity_id=user.id,
    )


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
