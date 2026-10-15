from datetime import date, datetime

from pydantic import BaseModel, Field


class SparSignatureOut(BaseModel):
    signature_image: str | None = None
    signatory_name: str | None = None
    signatory_title: str | None = None
    updated_at: datetime | None = None
    updated_by_name: str | None = None


class SparSignatureIn(BaseModel):
    signatory_name: str = Field(min_length=1, max_length=120)
    signatory_title: str | None = Field(default=None, max_length=120)
    # PNG data URL, drawn on the pad or converted from an uploaded image in the browser.
    signature_image: str = Field(min_length=1, max_length=400_000)


class FinalDatesOut(BaseModel):
    dates: list[date]
    # The supplier's next delivery date that isn't final yet, and when it will be.
    next_delivery_date: date | None = None
    next_final_at: datetime | None = None
    cutoff_label: str
    # Downloads need SPAR's signature, set on Admin > Settings.
    signature_ready: bool


class FinalPriceLineOut(BaseModel):
    product_id: int
    product_code: str
    category: str
    product_description: str
    unit_code: str
    your_price: float
    adjusted_price: float | None = None
    final_price: float
    basis: str


class SupplierSignatureOut(BaseModel):
    price_sheet_id: int
    signer_name: str | None = None
    signed_at: datetime | None = None
    signature_image: str


class FinalPriceListOut(BaseModel):
    supplier_name: str
    delivery_date: date
    finalized_at: datetime
    reference: str
    lines: list[FinalPriceLineOut]
    spar_signature: SparSignatureOut
    supplier_signatures: list[SupplierSignatureOut]
