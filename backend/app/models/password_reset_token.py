from datetime import datetime

from sqlalchemy import String, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PasswordResetToken(Base):
    """
    A one-time, time-limited token that lets someone who cannot log in at
    all set a new password for one specific account — the break-glass path
    for a locked-out account (Admin, most often, since there's no other
    standing admin login) when there's no email-based recovery available
    (this deployment has no SMTP configured) and no self-service "forgot
    password" otherwise.

    Only ever created by scripts/generate_recovery_token.py, run by
    whoever has direct server access — never by an API call. That's
    deliberate: issuing a recovery token already requires the same level
    of access a raw database password reset would need, so this doesn't
    lower the security bar, it just makes the recovery step safe,
    single-use, and auditable instead of a raw SQL UPDATE.

    Only the SHA-256 hash of the actual token is stored, never the token
    itself, the same way password_hash is never plaintext — reading this
    table (even with full DB access) is not enough to redeem a token.
    """

    __tablename__ = "password_reset_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Null until redeemed. A used (or expired) token is never valid again —
    # redemption checks both, not just presence of the row.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
