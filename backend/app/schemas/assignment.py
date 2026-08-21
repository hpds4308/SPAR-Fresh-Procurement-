from datetime import date
from pydantic import BaseModel, Field, field_validator


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
    assignments: list[AssignmentEntry]
    assigned_quantity: float
    fully_assigned: bool


class AssignmentIn(BaseModel):
    supplier_id: int
    quantity: float = Field(gt=0)
    agreed_price: float = Field(gt=0)

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
