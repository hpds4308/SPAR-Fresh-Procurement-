from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LocalMarketPrice(Base):
    """
    One product's wholesale prices on one HARTI daily bulletin, across the
    four markets Admin tracks (Dambulla, Thambuththegama, Keppetipola,
    Nuwara Eliya) — imported by harti_import_service.py and shown on the
    Admin Local Market Prices page. A market with no price that day has
    both its min and max left null.

    Each market's average is its midpoint ((min + max) / 2) and isn't
    stored; final_average is the mean of the markets that have a price,
    and is also written to market_reference_prices (source LOCAL_MARKET)
    for the Price History trend.

    dc_code, system_name and pdf_name come from the import's own product
    mapping, so a row stands on its own even if its DC code has no
    matching product (product_id null) in this database.
    """

    __tablename__ = "local_market_prices"
    __table_args__ = (UniqueConstraint("report_date", "dc_code", name="uq_local_market_price_date_dc_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    dc_code: Mapped[str] = mapped_column(String(30), nullable=False)
    system_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pdf_name: Mapped[str] = mapped_column(String(200), nullable=False)
    dambulla_min: Mapped[float | None] = mapped_column(Numeric(10, 2))
    dambulla_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    thambuththegama_min: Mapped[float | None] = mapped_column(Numeric(10, 2))
    thambuththegama_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    keppetipola_min: Mapped[float | None] = mapped_column(Numeric(10, 2))
    keppetipola_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    nuwara_eliya_min: Mapped[float | None] = mapped_column(Numeric(10, 2))
    nuwara_eliya_max: Mapped[float | None] = mapped_column(Numeric(10, 2))
    final_average: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    imported_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
