from datetime import datetime, date

from sqlalchemy import JSON, Date, DateTime, Integer, Numeric, String, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PurchaseOrder(Base):
    """
    The formal purchase order Admin issues to a supplier once their order
    for a delivery date is settled (Supplier Orders). One PO per
    (supplier, delivery_date), numbered PO-<yymmdd>-<supplier_code>; each
    branch it delivers to gets its own branch PO under it, numbered
    <po_number>-<branch_code> — derived from the lines, not stored.

    `items` is a frozen snapshot of the supplier_order_items lines and
    their resolved prices at issue time, so the PO never silently changes
    when the live order is edited afterwards. `snapshot_hash` fingerprints
    those lines; comparing it with the live order is how an issued PO is
    flagged as out of date. Re-issuing replaces the snapshot and bumps
    `revision` — the PO number stays the same.

    Status: ISSUED, or CANCELLED (Admin withdrew it; re-issuing reopens it).
    """

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("supplier_id", "delivery_date", name="uq_purchase_order_supplier_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    po_number: Mapped[str] = mapped_column(String(60), unique=True, nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ISSUED")
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    total_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    issued_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cancelled_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
