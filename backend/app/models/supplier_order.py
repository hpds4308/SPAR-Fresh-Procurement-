from datetime import datetime, date

from sqlalchemy import Numeric, Date, DateTime, String, Text, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierOrderItem(Base):
    """
    Admin's direct order to a supplier for one branch's requirement of one
    product, for one delivery date. Unlike SupplierAssignment (which splits
    a product's *total* demand across suppliers without branch detail),
    this preserves exactly which branch each line came from — so both
    Admin and the Supplier can see the order broken down branch by branch,
    matching how the supplier will actually need to pack and deliver it.

    agreed_price is optional: Admin can create the order first and settle
    price afterwards (e.g. against the supplier's later price submission).

    Resubmitting the full set of lines for a (supplier, delivery_date) via
    the admin builder replaces them (upsert on the natural key below) —
    same replace-the-whole-set convention as SupplierAssignment.
    """

    __tablename__ = "supplier_order_items"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "branch_id", "product_id", "delivery_date",
            name="uq_supplier_order_item",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(10), nullable=False)  # snapshot, same reasoning as OrderLine
    agreed_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
