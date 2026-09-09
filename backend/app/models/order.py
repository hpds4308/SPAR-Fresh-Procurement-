from datetime import datetime, date

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Order(Base):
    """
    A single branch's order for a single order date. Branches submit
    before the daily cutoff (see settings.BRANCH_ORDER_DEADLINE) and the
    order is always for delivery two days later (delivery date = order
    date + 2) — the same lead time suppliers get for pricing (see
    pricing_service.py), so both sides are submitted the same day for the
    same future delivery date. Branches never choose a supplier; Admin
    assigns supplier(s) to each line in a later phase.

    One order per branch per order_date, enforced by the
    uq_orders_branch_order_date unique constraint (see migration 0009).
    That's the "once a day" business key — it deliberately does NOT
    constrain on delivery_date, since a handful of legacy rows from
    before the +2 rule existed have order_date == delivery_date, and must
    never block a genuinely new order that happens to share their
    delivery_date.
    """

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)  # date it was placed
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)  # now: order_date + 2 days
    # SUBMITTED -> ASSIGNED (admin has assigned suppliers) -> CONFIRMED
    # (branch has confirmed what actually arrived)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SUBMITTED")
    notes: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    # Snapshot of the unit code at order time, so later unit-master edits
    # never silently change the meaning of a historical order line.
    unit_code: Mapped[str] = mapped_column(String(10), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # Filled in when the branch confirms delivery (Phase 5f). Null until
    # then. Can differ from `quantity` — that's the whole point, it's how
    # shortages/overages get caught and recorded.
    received_quantity: Mapped[float | None] = mapped_column(Numeric(10, 2))
    receipt_notes: Mapped[str | None] = mapped_column(Text)
