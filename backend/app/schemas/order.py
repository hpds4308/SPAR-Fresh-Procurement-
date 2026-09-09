from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator

from app.schemas._limits import MAX_NUMERIC_10_2


class OrderLineCreate(BaseModel):
    product_id: int
    quantity: float = Field(gt=0, le=MAX_NUMERIC_10_2, description="Must be greater than zero.")
    notes: str | None = None

    @field_validator("quantity")
    @classmethod
    def round_quantity(cls, v: float) -> float:
        return round(v, 2)


class OrderCreate(BaseModel):
    lines: list[OrderLineCreate]
    notes: str | None = None

    @field_validator("lines")
    @classmethod
    def at_least_one_line(cls, v: list[OrderLineCreate]) -> list[OrderLineCreate]:
        if not v:
            raise ValueError("An order must contain at least one product line.")
        return v


class OrderLineOut(BaseModel):
    id: int
    product_id: int
    product_code: str
    product_description: str
    quantity: float
    unit_code: str
    notes: str | None = None
    received_quantity: float | None = None
    receipt_notes: str | None = None

    class Config:
        from_attributes = True


class OrderOut(BaseModel):
    id: int
    branch_id: int
    branch_name: str
    order_date: date
    delivery_date: date
    status: str
    notes: str | None = None
    submitted_by_username: str
    confirmed_at: str | None = None
    confirmed_by_username: str | None = None
    lines: list[OrderLineOut]

    class Config:
        from_attributes = True


class OrderSummary(BaseModel):
    id: int
    branch_id: int
    branch_name: str
    order_date: date
    delivery_date: date
    status: str
    line_count: int

    class Config:
        from_attributes = True


class OrderWindowOut(BaseModel):
    """Tells the branch UI whether ordering is currently open, and for what date."""

    is_open: bool
    delivery_date: date
    cutoff_time: str  # "HH:MM", 24h, local business time
    server_time: str  # ISO datetime, for client-side countdowns


class MatrixBranchColumn(BaseModel):
    branch_id: int
    branch_code: str
    branch_name: str


class MatrixRow(BaseModel):
    product_id: int
    product_code: str
    category_name: str
    description: str
    unit_code: str
    # branch_id (as string, since JSON object keys are strings) -> quantity
    quantities: dict[str, float]


class OrderMatrixOut(BaseModel):
    delivery_date: date
    branches: list[MatrixBranchColumn]
    rows: list[MatrixRow]
    available_delivery_dates: list[date]


class DeliveryLineConfirm(BaseModel):
    product_id: int
    received_quantity: float = Field(
        ge=0, le=MAX_NUMERIC_10_2, description="Actual quantity received; 0 if nothing arrived."
    )
    notes: str | None = None

    @field_validator("received_quantity")
    @classmethod
    def round_quantity(cls, v: float) -> float:
        return round(v, 2)


class DeliveryConfirmRequest(BaseModel):
    lines: list[DeliveryLineConfirm]

    @field_validator("lines")
    @classmethod
    def at_least_one_line(cls, v: list[DeliveryLineConfirm]) -> list[DeliveryLineConfirm]:
        if not v:
            raise ValueError("Confirm at least one product line.")
        return v


class ExcelOrderLinePreview(BaseModel):
    """
    One row of an uploaded order Excel, after validation — used only to
    show the branch user a preview before anything is saved. product_id
    is None whenever the row couldn't be matched/parsed cleanly, in which
    case `error` explains why and quantity/unit_code are whatever could
    still be read for context, not necessarily usable.
    """

    row_number: int
    product_code: str
    description: str | None = None
    unit_code: str | None = None
    quantity: float | None = None
    product_id: int | None = None
    error: str | None = None


class ExcelOrderPreviewOut(BaseModel):
    """
    Result of parsing an uploaded order Excel — never saves anything by
    itself. The branch user reviews this (rows with no `error` become
    prefilled quantities on the normal order form) and still has to press
    Save/Submit themselves, going through the exact same
    save_draft_order/create_order path as manual entry — the upload is
    purely an alternate way to fill in quantities, not a separate way to
    place an order.
    """

    lines: list[ExcelOrderLinePreview]
    valid_line_count: int
    error_count: int


class OrderDeadlineExceptionRequest(BaseModel):
    """Which order_date to grant (or revoke) the exception for — almost
    always today, but not assumed, so Admin can act on a date after the
    fact (e.g. it's now past midnight and yesterday's cutoff already
    passed) without this schema needing to change."""

    order_date: date


class OrderDeadlineExceptionOut(BaseModel):
    branch_id: int
    branch_name: str
    order_date: date
    granted_by_username: str
    created_at: datetime
