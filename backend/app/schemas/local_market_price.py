from datetime import date, datetime

from pydantic import BaseModel


class MarketRangeOut(BaseModel):
    min: float
    max: float
    average: float  # the market's midpoint, (min + max) / 2


class LocalMarketPriceOut(BaseModel):
    dc_code: str
    system_name: str
    pdf_name: str  # the product's label in the HARTI bulletin
    product_id: int | None
    category_name: str | None
    # One entry per market; null when that market had no price that day.
    dambulla: MarketRangeOut | None
    thambuththegama: MarketRangeOut | None
    keppetipola: MarketRangeOut | None
    nuwara_eliya: MarketRangeOut | None
    final_average: float  # mean of the markets above that have a price


class LocalMarketReportOut(BaseModel):
    # null only when nothing has ever been imported.
    report_date: date | None
    imported_at: datetime | None
    available_dates: list[date]  # newest first
    rows: list[LocalMarketPriceOut]


class LocalMarketUnmatched(BaseModel):
    dc_code: str
    system_name: str


class LocalMarketImportResultOut(BaseModel):
    report_date: date
    saved: int
    # Mapped products in the bulletin with no price in any of the four markets.
    not_priced: list[str]
    # Saved, but their DC code has no product in this database — so no
    # Price History entry was written for them.
    unmatched: list[LocalMarketUnmatched]
