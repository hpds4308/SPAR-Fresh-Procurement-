from datetime import datetime, date

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OrderDeadlineException(Base):
    """
    Admin grants ONE branch permission to submit (or keep editing) an order
    for ONE specific order_date, past the normal daily cutoff
    (settings.BRANCH_ORDER_DEADLINE). The row's mere existence is what
    matters — order_service.get_order_window checks for one and, if found,
    reports the window as open for that branch regardless of the clock.
    It does NOT change the delivery_date math (still order_date + 2) or
    grant anything for any other branch or date — a one-time, narrowly
    scoped override, not a change to the cutoff rule itself.
    """

    __tablename__ = "order_deadline_exceptions"
    __table_args__ = (
        UniqueConstraint("branch_id", "order_date", name="uq_order_deadline_exception_branch_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    granted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
