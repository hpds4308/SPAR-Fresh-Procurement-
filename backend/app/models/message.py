from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Message(Base):
    """
    A single chat message in one of three kinds of thread:
      - Admin <-> one supplier: only supplier_id set
      - Admin <-> one branch:   only branch_id set
      - one supplier <-> one branch: both set (Admin can read these, but
        doesn't post in them)
    At least one of supplier_id/branch_id is always set (DB check
    constraint). Every Admin user shares a thread, as does every user of
    that supplier/branch. Not per-order, not
    per-product; just one running conversation per counterparty, which is
    the simplest model that matches "Admin talks to Supplier/Branch"
    rather than needing a separate thread per topic.
    """

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"), nullable=True)
    sender_role: Mapped[str] = mapped_column(String(20), nullable=False)  # "ADMIN" | "SUPPLIER" | "BRANCH"
    sender_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set when the *other* side has viewed this message — read_by_admin_at
    # only ever gets set on a message sent by the supplier/branch, and
    # vice versa. A message can never mark itself read; that would be
    # meaningless.
    read_by_admin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_by_supplier_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_by_branch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageAttachment(Base):
    """
    A photo or file attached to a chat message. Uploaded on its own first
    (message_id still null, visible only to the uploader), then linked to
    the message when it's sent. Stored in the database itself — `data` is
    deferred so listing messages never loads the file bytes.
    """

    __tablename__ = "message_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"))
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, deferred=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
