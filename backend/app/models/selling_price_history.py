from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SellingPriceHistory(Base):
    """
    One row per product each time Update Selling Prices gives it a new or
    changed price (unchanged prices add nothing). The price that applied
    on a date is the latest row published by the end of that day.
    """

    __tablename__ = "selling_price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int | None] = mapped_column(Integer)  # master_data_submissions.version it came from
