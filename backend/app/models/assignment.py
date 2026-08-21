from datetime import datetime, date

from sqlalchemy import Numeric, Date, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierAssignment(Base):
    """
    Admin's decision on how much of a product's total demand (summed
    across all branches, for one delivery date) goes to a given supplier,
    and at what agreed price. Agreed price is stored separately from the
    supplier's original quote in supplier_prices — it may be the same
    number, or it may reflect Admin negotiating the price down (or up).

    One product/delivery_date can have several rows here (one per
    supplier) when Admin splits the quantity across suppliers.
    """

    __tablename__ = "supplier_assignments"
    __table_args__ = (
        UniqueConstraint(
            "product_id", "delivery_date", "supplier_id", name="uq_assignment_product_date_supplier"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    agreed_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    assigned_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
