from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RevokedToken(Base):
    """
    Deny-list of individual refresh tokens revoked at logout (by their `jti` claim).

    Only that one session dies: branch/supplier logins are shared by several staff and devices, so
    logging out on one machine must not sign everybody else out. "Revoke everything" events
    (password change/reset, deactivation) use users.token_version instead. Rows are only needed
    until the token would have expired anyway, so expired rows are purged opportunistically.
    """

    __tablename__ = "revoked_tokens"
    __table_args__ = (Index("ix_revoked_tokens_expires_at", "expires_at"),)

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
