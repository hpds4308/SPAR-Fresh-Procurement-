from datetime import date
from pydantic import BaseModel, Field, field_validator


class OrderLineCreate(BaseModel):
    product_id: int
    quantity: float = Field(gt=0, description="Must be greater than zero.")
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
    received_quantity: float = Field(ge=0, description="Actual quantity received; 0 if nothing arrived.")
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
