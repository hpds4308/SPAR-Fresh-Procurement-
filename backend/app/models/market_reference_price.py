from datetime import date, datetime

from sqlalchemy import Numeric, Date, DateTime, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MarketReferencePrice(Base):
    """
    A reference price for one product, for one delivery date, shown
    alongside supplier quotes on the Admin pricing pages purely as a
    comparison point (e.g. "Keells sells this to consumers at Rs. X, so
    paying our supplier Rs. Y makes sense"). Nothing else in the system
    reads or depends on this table — it's a pure reference, never used
    in any calculation, order, or price comparison logic.

    `source` distinguishes where a row came from: "KEELLS" is entered by
    hand (competitor retail pricing); "LOCAL_MARKET" is populated by the
    daily wholesale-market auto-import (see harti_import_service.py),
    which merges HARTI/Dambulla/Keppetipola/CBSL/GoviSaviya data.
    """

    __tablename__ = "market_reference_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "source", "delivery_date", name="uq_reference_price_product_source_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="KEELLS")
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
