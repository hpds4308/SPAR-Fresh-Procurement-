from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# Label colors Admin can pick for a promotion; the frontend maps each one
# to its badge classes.
PromotionColor = Literal["blue", "green", "yellow", "red", "purple", "orange", "pink", "teal"]


class PromotionTypeIn(BaseModel):
    name: str = Field(max_length=60)
    color: PromotionColor

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Enter a promotion name.")
        return v


class PromotionTypeOut(BaseModel):
    id: int
    name: str
    color: PromotionColor
    product_count: int  # products this promotion is currently set on


class PromotionLineIn(BaseModel):
    product_id: int
    promotion_type_id: int
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def check_range(self):
        if self.end_date < self.start_date:
            raise ValueError("End date can't be before the start date.")
        return self


class PromotionSave(BaseModel):
    # The complete promotion list — replaces whatever was saved before. A
    # product left out has its promotion removed; an empty list clears all.
    lines: list[PromotionLineIn]


class PromotionOut(BaseModel):
    product_id: int
    promotion_type_id: int
    promotion_name: str
    color: PromotionColor
    start_date: date
    end_date: date
