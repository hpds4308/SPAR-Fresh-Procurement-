from datetime import datetime, date

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MissedOrderNotice(Base):
    """
    Recorded by auto_order_service when a branch missed the cutoff for
    order_date but nothing could be auto-submitted for it (no draft and no
    previous order to copy) — so Admin is told the branch has no order,
    instead of it silently going without. Shown on the Admin dashboard
    until Admin dismisses it (reviewed_at) or an order for that branch and
    date appears (e.g. Admin adds items for them from the order matrix).
    """

    __tablename__ = "missed_order_notices"
    __table_args__ = (
        UniqueConstraint("branch_id", "order_date", name="uq_missed_order_notice_branch_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
