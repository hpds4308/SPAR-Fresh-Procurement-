from datetime import datetime

from sqlalchemy import String, ForeignKey, DateTime, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductCategory(Base):
    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)


class ProductUnit(Base):
    __tablename__ = "product_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    # POS code intentionally nullable — some source records genuinely lack one.
    # Never invent a replacement value; use pos_code_flag to surface the issue instead.
    pos_code: Mapped[str | None] = mapped_column(String(30))
    pos_code_flag: Mapped[str | None] = mapped_column(String(20))  # MISSING, NA, or NULL if fine
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("product_categories.id"), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(100))
    unit_id: Mapped[int] = mapped_column(ForeignKey("product_units.id"), nullable=False)
    default_supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    # Margin/pricing reference fields for the Master Data Sheet — set and
    # maintained by Admin, independent of any supplier's quoted price.
    # target_gp_percent: the gross-profit fraction Admin wants on this
    # item (e.g. 0.30 = 30%), not tied to any date.
    target_gp_percent: Mapped[float | None] = mapped_column(Numeric(5, 4))
    # selling_price: current retail selling price to the customer.
    selling_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    # reference_cost_price: Admin's own reference cost figure, independent
    # of (and not derived from) any supplier's submitted or adjusted price
    # — those stay visible alongside it for comparison, never overwritten.
    reference_cost_price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
