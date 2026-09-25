from datetime import datetime
from pydantic import BaseModel, Field, field_validator

from app.schemas._limits import MAX_NUMERIC_10_2


class SafetyStockLineIn(BaseModel):
    product_id: int
    quantity: float = Field(gt=0, le=MAX_NUMERIC_10_2, description="Must be greater than zero.")

    @field_validator("quantity")
    @classmethod
    def round_quantity(cls, v: float) -> float:
        return round(v, 2)


class SafetyStockSave(BaseModel):
    # The branch's complete safety-stock list — replaces whatever was
    # saved before. A product left out is cleared; an empty list clears all.
    lines: list[SafetyStockLineIn]


class SafetyStockOut(BaseModel):
    # product_id -> quantity; a missing product_id means none set.
    quantities: dict[int, float]
    updated_at: datetime | None = None
    updated_by_username: str | None = None
