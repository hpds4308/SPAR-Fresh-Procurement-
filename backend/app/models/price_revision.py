from datetime import datetime, date

from sqlalchemy import JSON, Date, DateTime, String, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierPriceRevision(Base):
    """
    One price sheet Admin sends to a supplier for approval: every adjusted
    price for that supplier and delivery date that wasn't already agreed,
    sent together so the supplier signs once, not once per item.

    `items` is a frozen snapshot of exactly what was sent (product, the
    supplier's own price, Admin's adjusted price) and `snapshot_hash` is a
    SHA-256 of it. The supplier's signature is recorded against that hash,
    so what they agreed to stays provable even after the live
    supplier_prices rows change or are deleted.

    Status lifecycle (see price_approval_service.py):
      PENDING   sent, waiting for the supplier
      APPROVED  supplier e-signed; locked. Admin editing any price on it
                voids it and the new figures must be sent and signed again.
      REJECTED  supplier declined, with a reason
      VOIDED    replaced by a newer sheet, or a price on it changed
      WITHDRAWN Admin took it back before the supplier responded
    A PENDING sheet whose delivery date has arrived is reported as EXPIRED
    (computed, not stored) and can no longer be signed — the supplier's
    own price applies instead.
    """

    __tablename__ = "supplier_price_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    delivery_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    sent_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Who approved/rejected, and when.
    responded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # E-signature evidence, set on approval only.
    signer_name: Mapped[str | None] = mapped_column(String(150))
    signature_image: Mapped[str | None] = mapped_column(Text)  # PNG data URL drawn by the signer
    signer_ip: Mapped[str | None] = mapped_column(String(255))  # X-Forwarded-For chain
    signer_user_agent: Mapped[str | None] = mapped_column(String(500))
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    # Why a sheet was VOIDED/WITHDRAWN, and when.
    closed_reason: Mapped[str | None] = mapped_column(String(255))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
