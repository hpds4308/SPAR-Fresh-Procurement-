from datetime import datetime, date

from sqlalchemy import Numeric, Date, DateTime, String, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierPrice(Base):
    """
    A supplier's quoted price for one product, for one delivery date.
    Submitted before the daily price cutoff (see settings.SUPPLIER_PRICE_DEADLINE,
    default 12:00 Asia/Colombo) for delivery the *next* day — same delivery-date
    convention as branch orders, so Admin can compare orders and prices for the
    same day side by side.

    Resubmitting before the cutoff updates the existing quote (upsert) rather
    than creating duplicates — a supplier only ever has one live price per
    product per delivery date.
    """

    __tablename__ = "supplier_prices"
    __table_args__ = (
        UniqueConstraint("supplier_id", "product_id", "delivery_date", name="uq_supplier_price_product_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    unit_code: Mapped[str] = mapped_column(String(10), nullable=False)  # snapshot, same reasoning as OrderLine
    # Admin's negotiated/adjusted price for this same supplier quote. Null
    # until Admin sets one — the supplier's original `price` above is never
    # overwritten, so both figures stay visible side by side (matches the
    # "Supplier Price" / "Adjusted Price" columns on the admin prices view).
    adjusted_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    adjusted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    adjusted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Null while the adjusted price is still a draft only Admin can see.
    # Set when Admin explicitly sends it — only then does it appear on the
    # supplier's own price view. Cleared automatically if adjusted_price is
    # cleared or changed, so the supplier never sees a stale sent price.
    sent_to_supplier_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
