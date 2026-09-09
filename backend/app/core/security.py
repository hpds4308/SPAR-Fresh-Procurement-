"""
Authentication & authorization primitives.

Password hashing: argon2 via passlib. Never store or log plaintext passwords.
JWT: short-lived access token + longer-lived refresh token. Tokens carry only
user id + role codes — never branch/supplier authorization decisions. Every
scoped query re-checks the user's branch_id/supplier_id against the database
on each request; nothing is trusted from the token beyond identity.
"""
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import UnauthorizedError, PermissionDeniedError
from app.models.user import User, Role, UserRole

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login", auto_error=False)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def hash_recovery_token(raw_token: str) -> str:
    """
    SHA-256 hex digest of a break-glass account-recovery token (see
    PasswordResetToken). A recovery token is already a high-entropy random
    string generated with secrets.token_urlsafe — unlike a human-chosen
    password, there's nothing to brute-force by guessing, so a fast hash
    is the right tool here, not argon2's deliberate slowness.
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "type": token_type, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _create_token(str(user_id), timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES), "access")


def create_refresh_token(user_id: int) -> str:
    return _create_token(str(user_id), timedelta(minutes=settings.REFRESH_TOKEN_EXPIRE_MINUTES), "refresh")


def decode_token(token: str, expected_type: str = "access") -> int:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise UnauthorizedError("Invalid or expired token.")
    if payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type.")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        raise UnauthorizedError("Invalid token payload.")


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise UnauthorizedError("Authentication is required.")
    user_id = decode_token(token, expected_type="access")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise UnauthorizedError("Account is inactive or does not exist.")
    return user


def get_user_roles(db: Session, user_id: int) -> list[str]:
    rows = (
        db.query(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .filter(UserRole.user_id == user_id)
        .all()
    )
    return [r[0] for r in rows]


def require_roles(*allowed_roles: str):
    """
    Dependency factory: use as Depends(require_roles("ADMIN")) on a route to
    restrict it to users holding one of the given role codes. Ownership of
    branch/supplier-scoped data is still re-checked separately in the
    service layer — this only gates the role, not the specific record.
    """

    def _dependency(
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        roles = get_user_roles(db, current_user.id)
        if not any(r in allowed_roles for r in roles):
            raise PermissionDeniedError("You do not have permission to perform this action.")
        return current_user

    return _dependency
