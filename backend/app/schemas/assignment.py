from datetime import date
from pydantic import BaseModel, Field, field_validator

from app.schemas._limits import MAX_NUMERIC_10_2


class SupplierQuote(BaseModel):
    supplier_id: int
    supplier_code: str
    supplier_name: str
    price: float
    unit_code: str


class AssignmentEntry(BaseModel):
    supplier_id: int
    quantity: float
    agreed_price: float
    # (second_lowest_price - agreed_price) * quantity — what this
    # assignment saved (or, negative, cost extra) versus the next-best
    # alternative quote. None when there's no second quote to compare
    # against (a single supplier, or none at all) — see
    # assignment_service.get_product_comparison.
    savings: float | None = None

    class Config:
        from_attributes = True


class ProductComparisonOut(BaseModel):
    product_id: int
    product_code: str
    description: str
    unit_code: str
    delivery_date: date
    total_demand: float
    quotes: list[SupplierQuote]
    # Next distinct price tier below the lowest quote, or None if fewer
    # than two distinct prices exist yet — same tie-breaking rule as
    # pricing_service.second_lowest_price (ties don't count as a second
    # tier), used here as the baseline for each assignment's savings.
    second_lowest_price: float | None = None
    assignments: list[AssignmentEntry]
    assigned_quantity: float
    fully_assigned: bool


class AssignmentIn(BaseModel):
    supplier_id: int
    quantity: float = Field(gt=0, le=MAX_NUMERIC_10_2)
    agreed_price: float = Field(gt=0, le=MAX_NUMERIC_10_2)

    @field_validator("quantity", "agreed_price")
    @classmethod
    def round_two(cls, v: float) -> float:
        return round(v, 2)


class SetAssignmentsRequest(BaseModel):
    assignments: list[AssignmentIn]

    @field_validator("assignments")
    @classmethod
    def unique_suppliers(cls, v: list[AssignmentIn]) -> list[AssignmentIn]:
        ids = [a.supplier_id for a in v]
        if len(ids) != len(set(ids)):
            raise ValueError("Each supplier can only appear once — combine into a single quantity.")
        return v


class MyAssignmentLine(BaseModel):
    product_id: int
    product_code: str
    description: str
    unit_code: str
    quantity: float
    agreed_price: float
    line_total: float


class MyAssignmentsOut(BaseModel):
    delivery_date: date | None
    lines: list[MyAssignmentLine]
    grand_total: float
    available_delivery_dates: list[date]


class SupplierAssignedProductOut(BaseModel):
    """One product Admin has already assigned to this supplier for this
    delivery date, via Product Assignment (Order Matrix) — powers the
    Supplier Order Builder's "Fill from assignments" action, so Admin
    doesn't have to re-decide branch-level quantities for something
    already committed to this supplier."""

    product_id: int
    quantity: float
    agreed_price: float
