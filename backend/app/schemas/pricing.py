from datetime import date
from pydantic import BaseModel, Field, field_validator

from app.schemas._limits import MAX_NUMERIC_10_2


class PriceEntry(BaseModel):
    product_id: int
    price: float = Field(gt=0, le=MAX_NUMERIC_10_2, description="Must be greater than zero.")

    @field_validator("price")
    @classmethod
    def round_price(cls, v: float) -> float:
        return round(v, 2)


class PriceSubmitRequest(BaseModel):
    prices: list[PriceEntry]

    @field_validator("prices")
    @classmethod
    def at_least_one(cls, v: list[PriceEntry]) -> list[PriceEntry]:
        if not v:
            raise ValueError("Submit at least one price.")
        return v


class SupplierPriceOut(BaseModel):
    id: int
    product_id: int
    product_code: str
    product_description: str
    unit_code: str
    price: float
    delivery_date: date
    # Only populated once Admin has explicitly sent an adjusted price —
    # a draft adjustment Admin hasn't sent yet never appears here.
    adjusted_price: float | None = None

    class Config:
        from_attributes = True


class PriceWindowOut(BaseModel):
    is_open: bool
    delivery_date: date
    cutoff_time: str  # "HH:MM"
    server_time: str  # ISO datetime
    # The delivery date of the most recently opened Mon/Wed/Fri submission
    # cycle (may equal delivery_date, or be earlier when today isn't a
    # submission day) — what Admin's browse views should default to.
    current_cycle_delivery_date: date


class LastPriceOut(BaseModel):
    """The most recent price a supplier has ever quoted for one product,
    regardless of which delivery date it was for — shown as a reference
    on the Submit Prices page so a supplier isn't starting from a blank
    slate every time the delivery window rolls forward."""

    product_id: int
    price: float
    delivery_date: date


class ReferencePriceOut(BaseModel):
    product_id: int
    source: str
    price: float
    delivery_date: date


class ReferencePriceSetRequest(BaseModel):
    price: float | None = Field(
        default=None,
        description="Null clears the reference price for this product/date.",
    )

    @field_validator("price")
    @classmethod
    def round_and_check(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("Reference price must be greater than zero.")
        if v > MAX_NUMERIC_10_2:
            raise ValueError(f"Reference price can't exceed {MAX_NUMERIC_10_2:,.2f}.")
        return round(v, 2)


class KeellsSyncUnmatched(BaseModel):
    dc_code: str
    system_name: str | None = None


class KeellsSyncResultOut(BaseModel):
    delivery_date: date
    matched: int
    saved: int
    skipped_rows: int
    unmatched: list[KeellsSyncUnmatched]


class AdminSupplierPriceOut(BaseModel):
    id: int
    supplier_id: int
    supplier_code: str
    supplier_name: str
    product_id: int
    product_code: str
    product_description: str
    category_name: str
    unit_code: str
    price: float
    adjusted_price: float | None = None
    sent_to_supplier: bool = False
    delivery_date: date
    is_lowest_for_product: bool
    # The next distinct price tier below the lowest for this product (None
    # if fewer than two distinct prices exist yet) — see list_all_prices
    # for why ties don't count as a second tier.
    second_lowest_price: float | None = None
    is_second_lowest_for_product: bool = False


class AdjustPriceRequest(BaseModel):
    adjusted_price: float | None = Field(
        default=None,
        description="Null clears the adjustment and reverts to the supplier's original price.",
    )

    @field_validator("adjusted_price")
    @classmethod
    def round_and_check(cls, v: float | None) -> float | None:
        if v is None:
            return None
        if v <= 0:
            raise ValueError("Adjusted price must be greater than zero.")
        if v > MAX_NUMERIC_10_2:
            raise ValueError(f"Adjusted price can't exceed {MAX_NUMERIC_10_2:,.2f}.")
        return round(v, 2)

