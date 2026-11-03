from datetime import date, datetime

from pydantic import BaseModel


class SellingPriceRowOut(BaseModel):
    product_id: int
    product_code: str
    pos_code: str | None
    description: str
    category_name: str
    unit_code: str
    selling_price: float | None  # None: nothing published for this product by that date
    published_at: datetime | None  # when this price was published


class SellingPriceListOut(BaseModel):
    on: date
    rows: list[SellingPriceRowOut]
