from datetime import date, datetime

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RevisionItemOut(BaseModel):
    supplier_price_id: int
    product_id: int
    product_code: str
    product_description: str
    unit_code: str
    supplier_price: float
    adjusted_price: float
    # The supplier's answer to this item once they've responded:
    # APPROVED / REJECTED, and for a rejected item, the final price they
    # gave instead (or None — their submitted price applies).
    decision: str | None = None
    counter_price: float | None = None


class RevisionSummaryOut(BaseModel):
    id: int
    supplier_id: int
    supplier_name: str
    delivery_date: date
    # PENDING / APPROVED / PARTIAL / REJECTED / VOIDED / WITHDRAWN, or
    # EXPIRED for a PENDING sheet whose delivery date has already arrived.
    status: str
    item_count: int
    approved_count: int = 0
    rejected_count: int = 0
    sent_at: datetime
    sent_by_name: str | None = None
    responded_at: datetime | None = None
    responded_by_name: str | None = None
    signer_name: str | None = None
    rejection_reason: str | None = None
    closed_reason: str | None = None
    # When a PENDING sheet stops being signable.
    expires_at: datetime


class RevisionDetailOut(RevisionSummaryOut):
    items: list[RevisionItemOut]
    snapshot_hash: str
    signature_image: str | None = None
    signer_ip: str | None = None
    signer_user_agent: str | None = None


class SendForApprovalRequest(BaseModel):
    supplier_id: int
    delivery_date: date


class ApproveRevisionRequest(BaseModel):
    # The hash of the sheet the supplier was looking at — if Admin changed
    # anything since, approval is refused rather than signing different figures.
    snapshot_hash: str = Field(min_length=64, max_length=64)
    # The agreement tick and drawn signature are all a supplier needs to
    # approve. A typed name and password re-entry are optional — still
    # recorded / verified when an older client sends them.
    signer_name: str | None = Field(default=None, max_length=150)
    # PNG data URL from the signature pad.
    signature_image: str = Field(max_length=400_000)
    password: str | None = Field(default=None, max_length=200)
    agreed: bool

    @field_validator("signer_name")
    @classmethod
    def strip_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return " ".join(v.split()) or None

    @field_validator("agreed")
    @classmethod
    def must_agree(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Tick the box to confirm you agree to these prices.")
        return v


class RejectRevisionRequest(BaseModel):
    snapshot_hash: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("Tell SPAR why you're rejecting these prices.")
        return v


class ItemDecisionIn(BaseModel):
    supplier_price_id: int
    decision: Literal["APPROVED", "REJECTED"]
    # Only for a rejected item: the supplier's own final price instead of
    # SPAR's. Left out, their submitted price applies.
    counter_price: float | None = Field(default=None, gt=0, lt=10_000_000)


class RespondRevisionRequest(BaseModel):
    """The supplier's item-by-item answer to a price sheet."""

    snapshot_hash: str = Field(min_length=64, max_length=64)
    items: list[ItemDecisionIn] = Field(min_length=1, max_length=1000)
    # Optional note to SPAR about the rejected items.
    note: str | None = Field(default=None, max_length=1000)
    # Needed only when at least one item is approved.
    agreed: bool = False
    signature_image: str | None = Field(default=None, max_length=400_000)

    @field_validator("note")
    @classmethod
    def strip_note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return v.strip() or None


class CountOut(BaseModel):
    count: int
