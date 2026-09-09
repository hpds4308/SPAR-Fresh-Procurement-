from datetime import datetime

from sqlalchemy import String, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    branch_name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    # The POS system's own location code (24X7Retail/Dynamic Web) — a
    # separate code space from branch_code, not assumed to match it. Null
    # until Admin sets it; stock-in-hand lookups are simply skipped for a
    # branch that doesn't have one yet.
    pos_location_code: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
