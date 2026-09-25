from datetime import date
from typing import Literal

from pydantic import BaseModel, model_validator

PromotionType = Literal["FRESH_CHOICE", "SPECIAL_WEEKEND", "SPECIAL"]


class PromotionLineIn(BaseModel):
    product_id: int
    promotion_type: PromotionType
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
    promotion_type: PromotionType
    start_date: date
    end_date: date
