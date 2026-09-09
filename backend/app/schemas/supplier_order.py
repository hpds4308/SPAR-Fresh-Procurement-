from datetime import date
from pydantic import BaseModel, Field, field_validator

from app.schemas._limits import MAX_NUMERIC_10_2


class SupplierOut(BaseModel):
    id: int
    supplier_code: str
    supplier_name: str
    status: str

    class Config:
        from_attributes = True


class SupplierOrderItemIn(BaseModel):
    branch_id: int
    product_id: int
    quantity: float = Field(gt=0, le=MAX_NUMERIC_10_2)
    agreed_price: float | None = Field(default=None, ge=0, le=MAX_NUMERIC_10_2)
    notes: str | None = None

    @field_validator("quantity", "agreed_price")
    @classmethod
    def round_two(cls, v: float | None) -> float | None:
        return round(v, 2) if v is not None else None


class SetSupplierOrderRequest(BaseModel):
    items: list[SupplierOrderItemIn]

    @field_validator("items")
    @classmethod
    def unique_branch_product(cls, v: list[SupplierOrderItemIn]) -> list[SupplierOrderItemIn]:
        keys = [(it.branch_id, it.product_id) for it in v]
        if len(keys) != len(set(keys)):
            raise ValueError("Each branch + product combination can only appear once per order.")
        return v


class SupplierOrderItemOut(BaseModel):
    id: int
    branch_id: int
    branch_name: str
    product_id: int
    product_code: str
    product_description: str
    category_name: str
    quantity: float
    unit_code: str
    agreed_price: float | None
    # What "Cost Price" actually shows: agreed_price (an explicit manual
    # override on this specific order line) if Admin set one; otherwise
    # Admin's sent Adjusted Price for that supplier's quote on this
    # product/date; otherwise the supplier's own submitted price. None
    # only if none of those three exist yet.
    effective_price: float | None
    # True when effective_price came from a DIFFERENT date than this
    # order's delivery_date (Submit Prices and Supplier Orders run on
    # different date conventions, so an exact match is often unavailable) —
    # the UI must show this as an estimate, not a confirmed price.
    price_is_estimated: bool = False
    price_as_of: date | None = None
    notes: str | None
    line_total: float | None


class SupplierOrderAdminOut(BaseModel):
    supplier_id: int
    supplier_name: str
    delivery_date: date
    items: list[SupplierOrderItemOut]


class BranchOrderGroup(BaseModel):
    branch_id: int
    branch_name: str
    items: list[SupplierOrderItemOut]
    branch_total: float


class MySupplierOrdersOut(BaseModel):
    delivery_date: date | None
    branches: list[BranchOrderGroup]
    grand_total: float
    available_delivery_dates: list[date]


class SupplierOrderSummaryOut(BaseModel):
    """One row per supplier for the Supplier-wise side of Admin Order
    History — mirrors OrderSummary on the Branch-wise side. Expanding a
    row calls the existing GET /supplier-orders/admin endpoint for the
    branch-by-branch detail, so this only needs to carry the summary."""

    supplier_id: int
    supplier_name: str
    delivery_date: date
    line_count: int
    total_value: float


class SupplierPricePreviewOut(BaseModel):
    """A supplier's resolved price for one product, shown as a reference
    column on the Order Builder before any order line is saved — same
    price-resolution rule as SupplierOrderItemOut.effective_price."""

    product_id: int
    price: float
    is_estimated: bool
    as_of: date
