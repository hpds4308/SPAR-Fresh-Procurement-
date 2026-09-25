from datetime import date
from decimal import ROUND_CEILING, Decimal
from typing import Literal

from pydantic import BaseModel, field_validator

from app.schemas._limits import MAX_NUMERIC_10_2


def round_up_to_10(price: float) -> float:
    """Selling prices are always rounded UP to the next multiple of 10
    (1342 -> 1350, 1350 stays 1350). Goes through the 2-dp string form
    first so float noise like 1000.0000000001 doesn't bump it to 1010."""
    d = Decimal(f"{price:.2f}")
    return float((d / 10).to_integral_value(rounding=ROUND_CEILING) * 10)


class MasterDataSupplierColumn(BaseModel):
    supplier_id: int
    supplier_name: str


class MasterDataRowOut(BaseModel):
    product_id: int
    product_code: str
    pos_code: str | None
    description: str
    category_name: str
    target_gp_percent: float  # e.g. 0.30 = 30%; defaults to 0.30 until Admin overrides
    selling_price: float | None
    computed_gp_percent: float | None  # (selling_price - cost_price) / selling_price, live-derived
    cost_price: float | None  # Highest current price among suppliers who've quoted this — never manually set
    # Which supplier's quote is currently winning Cost Price, and the delivery
    # date they submitted it for — None whenever cost_price itself is None.
    cost_price_supplier_name: str | None = None
    cost_price_date: date | None = None
    # One entry per active supplier — that supplier's most recent Adjusted
    # Price (or their submitted price if never adjusted) for this product,
    # any date. Purely a read-only mirror of Supplier Prices; edit there,
    # not here. None means that supplier has never quoted this product.
    supplier_prices: dict[int, float | None]


class MasterDataSheetOut(BaseModel):
    suppliers: list[MasterDataSupplierColumn]
    rows: list[MasterDataRowOut]


MasterDataField = Literal["target_gp_percent", "selling_price"]


class MasterDataFieldUpdateRequest(BaseModel):
    """One field, one value — matches the inline-edit-one-cell pattern used
    throughout this app (e.g. Adjusted Price). Null clears the field.
    cost_price and pos_code deliberately aren't editable here — cost_price
    is always derived (see MasterDataField), and pos_code is fixed,
    sourced from the original uploaded product data and never edited
    in-app (see restore_pos_codes.py if it ever needs re-syncing)."""

    field: MasterDataField
    value: str | float | None = None

    @field_validator("value")
    @classmethod
    def validate_by_field(cls, v, info):
        field = info.data.get("field")
        if v is None:
            return v
        if field == "target_gp_percent":
            fv = float(v)
            if not (0 <= fv <= 1):
                raise ValueError("Target GP% must be between 0 and 1 (e.g. 0.30 for 30%).")
            return fv
        if field == "selling_price":
            fv = float(v)
            if fv <= 0:
                raise ValueError("Price must be greater than zero.")
            fv = round_up_to_10(fv)
            if fv > MAX_NUMERIC_10_2:
                raise ValueError(f"Price can't exceed {MAX_NUMERIC_10_2:,.2f}.")
            return fv
        return str(v)
