from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmailLog(Base):
    """
    One email the app sent (or tried to) — see notification_service.py.
    Scheduled reminders carry a dedupe_key so each goes out only once,
    however often the scheduler wakes up or the backend restarts.
    """

    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    recipient: Mapped[str] = mapped_column(String(500), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    # SENT, FAILED (the email service refused it), or SKIPPED (email isn't configured).
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
