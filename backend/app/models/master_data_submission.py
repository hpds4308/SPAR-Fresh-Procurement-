from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MasterDataSubmission(Base):
    """
    One "Send to Master Data" by Admin: a numbered copy of the Master Data
    Sheet exactly as it was sent. The Master Data Team always works from
    the highest version; older ones stay as history. Products themselves
    are never copied into new rows — only this read-only snapshot.
    """

    __tablename__ = "master_data_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    sent_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    product_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sheet: Mapped[dict] = mapped_column(JSON, nullable=False)  # MasterDataSheetOut as JSON
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_summary: Mapped[dict | None] = mapped_column(JSON)
