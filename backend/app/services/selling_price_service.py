"""
Branch "Selling Price" tab: the selling prices the Master Data Team
published, for every active product, as they stood on a chosen date
(Asia/Colombo business day). Read-only — only publishing changes them.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.product import Product, ProductCategory, ProductUnit
from app.models.selling_price_history import SellingPriceHistory
from app.schemas.selling_price import SellingPriceListOut, SellingPriceRowOut

BUSINESS_TZ = ZoneInfo("Asia/Colombo")


def list_selling_prices(db: Session, on: date | None = None) -> SellingPriceListOut:
    on = on or datetime.now(BUSINESS_TZ).date()
    end_of_day = datetime.combine(on + timedelta(days=1), time.min, tzinfo=BUSINESS_TZ)

    # Latest publication per product up to the end of that day.
    latest = (
        db.query(
            SellingPriceHistory.product_id,
            func.max(SellingPriceHistory.published_at).label("published_at"),
        )
        .filter(SellingPriceHistory.published_at < end_of_day)
        .group_by(SellingPriceHistory.product_id)
        .subquery()
    )
    prices = {
        row.product_id: row
        for row in db.query(SellingPriceHistory)
        .join(
            latest,
            (SellingPriceHistory.product_id == latest.c.product_id)
            & (SellingPriceHistory.published_at == latest.c.published_at),
        )
        .all()
    }

    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE")
        .order_by(Product.category_id, Product.description)
        .all()
    )
    rows = []
    for p in products:
        h = prices.get(p.id)
        rows.append(
            SellingPriceRowOut(
                product_id=p.id,
                product_code=p.product_code,
                pos_code=p.pos_code,
                description=p.description,
                category_name=categories.get(p.category_id, "—"),
                unit_code=units.get(p.unit_id, "—"),
                selling_price=float(h.price) if h else None,
                published_at=h.published_at if h else None,
            )
        )
    return SellingPriceListOut(on=on, rows=rows)
