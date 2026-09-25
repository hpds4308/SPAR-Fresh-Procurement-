from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BranchSafetyStock(Base):
    """
    A branch's own safety-stock level for one product — the minimum it
    wants to keep on hand. One row per (branch, product), not per day: the
    figure stays in place day after day until the branch edits it again
    (or clears it). A product with no row simply has no safety stock set.
    """

    __tablename__ = "branch_safety_stock"
    __table_args__ = (UniqueConstraint("branch_id", "product_id", name="uq_branch_safety_stock_branch_product"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(ForeignKey("branches.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    updated_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
