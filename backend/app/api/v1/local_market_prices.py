"""
Admin Local Market Prices — wholesale prices from HARTI's daily bulletin
in four markets (Dambulla, Thambuththegama, Keppetipola, Nuwara Eliya),
with each market's average and the final average across them. See
harti_import_service.py for how a bulletin is fetched and read.
"""
import io
from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import NotFoundError, ValidationFailedError
from app.core.security import require_roles
from app.models.product import Product, ProductCategory
from app.models.user import User
from app.schemas.local_market_price import (
    LocalMarketImportResultOut,
    LocalMarketPriceOut,
    LocalMarketReportOut,
    MarketRangeOut,
)
from app.services import harti_import_service

router = APIRouter(prefix="/local-market-prices", dependencies=[Depends(require_roles("ADMIN"))])


def _range_out(row, market_key: str) -> MarketRangeOut | None:
    price_range = harti_import_service.market_range(row, market_key)
    if price_range is None:
        return None
    return MarketRangeOut(min=float(price_range.min), max=float(price_range.max), average=float(price_range.average))


@router.get("", response_model=LocalMarketReportOut)
def get_local_market_prices(report_date: date | None = None, db: Session = Depends(get_db)):
    """One bulletin's prices — the newest imported bulletin if no report_date is given."""
    report_date, rows = harti_import_service.get_report(db, report_date)
    product_ids = [r.product_id for r in rows if r.product_id is not None]
    categories = dict(
        db.query(Product.id, ProductCategory.name)
        .join(ProductCategory, ProductCategory.id == Product.category_id)
        .filter(Product.id.in_(product_ids))
        .all()
    )
    return LocalMarketReportOut(
        report_date=report_date,
        imported_at=max((r.imported_at for r in rows), default=None),
        available_dates=harti_import_service.latest_report_dates(db),
        rows=[
            LocalMarketPriceOut(
                dc_code=r.dc_code,
                system_name=r.system_name,
                pdf_name=r.pdf_name,
                product_id=r.product_id,
                category_name=categories.get(r.product_id),
                dambulla=_range_out(r, "dambulla"),
                thambuththegama=_range_out(r, "thambuththegama"),
                keppetipola=_range_out(r, "keppetipola"),
                nuwara_eliya=_range_out(r, "nuwara_eliya"),
                final_average=float(r.final_average),
            )
            for r in rows
        ],
    )


@router.post("/sync", response_model=LocalMarketImportResultOut)
async def sync_from_harti(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Downloads HARTI's newest English daily bulletin right now instead of
    waiting for the scheduled import, and replaces that report date's
    prices with it. Network-bound (two requests to harti.gov.lk), so it
    runs off the event loop.
    """
    try:
        result = await run_in_threadpool(harti_import_service.run_import, db, admin)
    except harti_import_service.HartiImportError as e:
        raise ValidationFailedError(str(e))
    return LocalMarketImportResultOut(**result)


@router.post("/upload", response_model=LocalMarketImportResultOut)
async def upload_bulletin(
    file: UploadFile = File(...),
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Imports a HARTI bulletin PDF Admin downloaded themselves — the
    fallback for when harti.gov.lk can't be reached from the server. The
    report date comes from the filename (HARTI's own filenames end in
    "(YYYY.MM.DD).pdf") or, failing that, from the PDF itself.
    """
    contents = await file.read(harti_import_service.MAX_PDF_BYTES + 1)
    try:
        result = await run_in_threadpool(harti_import_service.import_pdf, db, admin, contents, file.filename)
    except harti_import_service.HartiImportError as e:
        raise ValidationFailedError(str(e))
    return LocalMarketImportResultOut(**result)


@router.get("/export")
def export_local_market_prices(report_date: date | None = None, db: Session = Depends(get_db)):
    """Same rows as GET /local-market-prices as .xlsx, in the standalone tool's layout ("YYYY.MM.DD.xlsx")."""
    report_date, rows = harti_import_service.get_report(db, report_date)
    if not rows:
        raise NotFoundError("No local market prices have been imported for that date.")
    filename = f"{report_date.strftime('%Y.%m.%d')}.xlsx"
    return StreamingResponse(
        io.BytesIO(harti_import_service.build_excel(report_date, rows)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
