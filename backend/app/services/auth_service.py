from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.errors import UnauthorizedError, ValidationFailedError
from app.core.security import verify_password, hash_password, create_access_token, create_refresh_token, get_user_roles
from app.core.audit import write_audit_log
from app.models.user import User

MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

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
