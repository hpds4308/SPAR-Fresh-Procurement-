from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PromotionType(Base):
    """
    A promotion Admin has created (e.g. "Fresh Choice"), with the color its
    label is shown in. Names are unique ignoring case. Deleting one removes
    it from every product it was set on.
    """

    __tablename__ = "promotion_types"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    color: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductPromotion(Base):
    """
    An admin-set promotion on one product, running from start_date to
    end_date inclusive, in Asia/Colombo business dates. At most one row per
    product. Branches see it as a label only while today is inside the
    range, so a promotion stops showing on its own once the end date has
    passed.
    """

    __tablename__ = "product_promotions"
    __table_args__ = (
        UniqueConstraint("product_id", name="uq_product_promotions_product"),
        CheckConstraint("end_date >= start_date", name="ck_product_promotions_date_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    promotion_type_id: Mapped[int] = mapped_column(
        ForeignKey("promotion_types.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    promotion_type: Mapped[PromotionType] = relationship(lazy="joined")
