from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductPromotion(Base):
    """
    An admin-set promotion on one product (FRESH_CHOICE, SPECIAL_WEEKEND or
    SPECIAL), running from start_date to end_date inclusive, in Asia/Colombo
    business dates. At most one row per product. Branches see it as a label
    only while today is inside the range, so a promotion stops showing on
    its own once the end date has passed.
    """

    __tablename__ = "product_promotions"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_product_promotions_product"),
        CheckConstraint("end_date >= start_date", name="ck_product_promotions_date_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    promotion_type: Mapped[str] = mapped_column(String(32), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
