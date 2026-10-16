import logging
from datetime import date

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ValidationFailedError
from app.core.security import get_current_user, require_roles
from app.models.pricing import SupplierPrice
from app.models.product import Product
from app.models.user import User
from app.schemas.pricing import (
    PriceSubmitRequest,
    SupplierPriceOut,
    PriceWindowOut,
    AdminSupplierPriceOut,
    AdjustPriceRequest,
    LastPriceOut,
    KeellsSyncResultOut,
    ReferencePriceOut,
    ReferencePriceSetRequest,
    ExcelPricePreviewOut,
    KeellsExcelImportOut,
    KeellsExcelPreviewOut,
)
from app.services import pricing_service
from app.services import price_approval_service
from app.services import keells_scrape_service
from app.services import keells_import_service

router = APIRouter(prefix="/pricing", dependencies=[Depends(get_current_user)])
logger = logging.getLogger("spar.pricing")


def _supplier_price_out(db: Session, rows: list[SupplierPrice]) -> list[SupplierPriceOut]:
    """A supplier only ever sees an adjusted price once it has been sent to them for approval."""
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_([r.product_id for r in rows])).all()}
    statuses = price_approval_service.row_statuses(db, rows)
    out = []
    for r in rows:
        sent = r.sent_to_supplier_at is not None and r.adjusted_price is not None
        status, revision, counter_price = statuses[r.id]
        out.append(
            SupplierPriceOut(
                id=r.id,
                product_id=r.product_id,
                product_code=products[r.product_id].product_code,
                product_description=products[r.product_id].description,
                unit_code=r.unit_code,
                price=float(r.price),
                delivery_date=r.delivery_date,
                adjusted_price=float(r.adjusted_price) if sent else None,
                approval_status=status if sent else None,
                revision_id=revision.id if sent and revision else None,
                counter_price=counter_price if sent else None,
            )
        )
    return out


@router.get("/window", response_model=PriceWindowOut)
def price_window(db: Session = Depends(get_db)):
    """Tells the supplier UI whether price submission is open right now, and for which delivery date."""
    return pricing_service.get_price_window(db)


@router.post("", response_model=list[SupplierPriceOut])
def submit_prices(
    payload: PriceSubmitRequest,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    rows = pricing_service.submit_prices(db, current_user, payload)
    return _supplier_price_out(db, rows)


# Generous ceiling for the price template — a few hundred products is well
# under 100 KB; this only rejects something clearly wrong before parsing.
MAX_PRICE_EXCEL_BYTES = 5 * 1024 * 1024


@router.get("/excel-template")
def download_price_template(
    current_user: User = Depends(require_roles("SUPPLIER", "ADMIN")),
    db: Session = Depends(get_db),
):
    """Blank price sheet (Product Code, Product, Price) listing every active product."""
    content = pricing_service.build_price_template(db)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="spar-price-template.xlsx"'},
    )


@router.post("/preview-excel", response_model=ExcelPricePreviewOut)
async def preview_price_excel(
    file: UploadFile = File(...),
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """
    Parses a filled-in price template into a row-by-row preview — never
    saves anything. The supplier confirms and the valid rows are submitted
    through POST /pricing, the same as manual entry.
    """
    contents = await file.read(MAX_PRICE_EXCEL_BYTES + 1)
    if len(contents) > MAX_PRICE_EXCEL_BYTES:
        raise ValidationFailedError("That file is too large — please upload the price template as-is.")
    # Logged either way so a supplier's "it didn't work" can be traced
    # without needing their file.
    try:
        result = await run_in_threadpool(pricing_service.parse_price_excel, db, current_user, contents)
    except ValidationFailedError as e:
        logger.warning(
            "Price upload rejected: supplier=%s file=%r bytes=%d reason=%s",
            current_user.supplier_id, file.filename, len(contents), e.message,
        )
        raise
    logger.info(
        "Price upload read: supplier=%s file=%r valid=%d errors=%d blank=%d",
        current_user.supplier_id, file.filename, result.valid_line_count, result.error_count, result.blank_price_count,
    )
    return result


@router.get("/mine", response_model=list[SupplierPriceOut])
def my_prices(
    delivery_date: date | None = None,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    rows = pricing_service.list_my_prices(db, current_user, delivery_date)
    return _supplier_price_out(db, rows)


@router.get("/mine/last", response_model=list[LastPriceOut])
def my_last_prices(
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """Most recent price ever submitted per product, regardless of delivery date — a reference for the form."""
    rows = pricing_service.get_last_prices(db, current_user)
    return [LastPriceOut(product_id=r.product_id, price=float(r.price), delivery_date=r.delivery_date) for r in rows]


@router.get("/admin", response_model=list[AdminSupplierPriceOut])
def admin_all_prices(
    delivery_date: date | None = None,
    supplier_id: int | None = None,
    product_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Every supplier's quoted price across the whole catalogue for one
    delivery date — the admin's browse/compare view, as opposed to
    /orders/admin/product/{id}/comparison which looks at one product at a time.
    start_date + end_date return every delivery date in that range instead.
    """
    rows = pricing_service.list_all_prices(db, delivery_date, supplier_id, product_id, start_date, end_date)
    return [AdminSupplierPriceOut(**row) for row in rows]


@router.get("/admin/export")
def admin_export_prices(
    delivery_date: date | None = None,
    supplier_id: int | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """The Supplier Prices table (with Keells and MKT prices) as .xlsx."""
    content, used_date = pricing_service.build_admin_prices_excel(db, delivery_date, supplier_id)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="supplier-prices-{used_date.isoformat()}.xlsx"'},
    )


@router.patch("/admin/{price_id}/adjust")
def admin_adjust_price(
    price_id: int,
    payload: AdjustPriceRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Set (or clear, with adjusted_price: null) Admin's negotiated price for
    one supplier quote. Stays a draft until sent for approval via
    POST /price-approvals/admin.
    """
    row = pricing_service.set_adjusted_price(db, admin, price_id, payload.adjusted_price)
    return {
        "id": row.id,
        "price": float(row.price),
        "adjusted_price": float(row.adjusted_price) if row.adjusted_price is not None else None,
        "sent_to_supplier": row.sent_to_supplier_at is not None,
    }


# ---- Market reference prices — e.g. Keells retail price (manual entry) or
# LOCAL_MARKET wholesale prices (daily auto-import, see harti_import_service.py) ----


@router.get("/reference", response_model=list[ReferencePriceOut])
def list_reference_prices(
    delivery_date: date,
    source: str = "KEELLS",
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    rows = pricing_service.list_reference_prices(db, delivery_date, source)
    return [
        ReferencePriceOut(product_id=r.product_id, source=r.source, price=float(r.price), delivery_date=r.delivery_date)
        for r in rows
    ]


@router.get("/reference/last", response_model=list[ReferencePriceOut])
def last_reference_prices(
    source: str = "KEELLS",
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Most recent reference price ever entered per product, any date — powers the carry-forward pre-fill."""
    rows = pricing_service.get_last_reference_prices(db, source)
    return [
        ReferencePriceOut(product_id=r.product_id, source=r.source, price=float(r.price), delivery_date=r.delivery_date)
        for r in rows
    ]


@router.get("/reference/history", response_model=list[ReferencePriceOut])
def reference_price_history(
    start_date: date,
    end_date: date,
    source: str = "KEELLS",
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every entry for one source across a date range — powers the Price History trend view."""
    rows = pricing_service.list_reference_price_history(db, source, start_date, end_date)
    return [
        ReferencePriceOut(product_id=r.product_id, source=r.source, price=float(r.price), delivery_date=r.delivery_date)
        for r in rows
    ]


@router.put("/reference/{product_id}", response_model=ReferencePriceOut | None)
def set_reference_price(
    product_id: int,
    payload: ReferencePriceSetRequest,
    delivery_date: date,
    source: str = "KEELLS",
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Set (or clear, with price: null) the manually-entered competitor price for one product/date."""
    row = pricing_service.set_reference_price(db, admin, product_id, delivery_date, payload.price, source)
    if row is None:
        return None
    return ReferencePriceOut(product_id=row.product_id, source=row.source, price=float(row.price), delivery_date=row.delivery_date)


@router.post("/reference/keells-sync", response_model=KeellsSyncResultOut)
async def sync_keells_prices(
    delivery_date: date | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Triggers an immediate Keells price scrape (see keells_scrape_service.py)
    instead of waiting for the scheduled daily worker — this is the fully
    automated path: no external script to run, no file to download and
    upload, just launch a headless browser server-side and upsert whatever
    it finds. Can take up to ~60s since it's a real page-by-page scrape.
    """
    # A blocked or failed scrape raises KeellsScrapeError: a 502 with a
    # readable message, and no prices changed.
    result = await run_in_threadpool(keells_scrape_service.run_scrape, db, admin, delivery_date)
    return KeellsSyncResultOut(
        delivery_date=result["delivery_date"],
        matched=result["matched"],
        saved=result["saved"],
        skipped_rows=result["skipped_no_price"],
        unmatched=result["unmatched"],
    )


# The scraper's file is ~10 KB for ~60 rows; this only rejects something clearly wrong.
MAX_KEELLS_EXCEL_BYTES = 5 * 1024 * 1024


async def _read_keells_upload(file: UploadFile) -> bytes:
    contents = await file.read(MAX_KEELLS_EXCEL_BYTES + 1)
    if len(contents) > MAX_KEELLS_EXCEL_BYTES:
        raise ValidationFailedError("That file is too large — please upload the Keells price file as the scraper made it.")
    return contents


@router.post("/reference/keells-excel/preview", response_model=KeellsExcelPreviewOut)
async def preview_keells_excel(
    delivery_date: date,
    file: UploadFile = File(...),
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Checks every row of a Keells price file for `delivery_date` — saves nothing."""
    contents = await _read_keells_upload(file)
    return await run_in_threadpool(keells_import_service.preview_keells_excel, db, delivery_date, contents)


@router.post("/reference/keells-excel/import", response_model=KeellsExcelImportOut)
async def import_keells_excel(
    delivery_date: date,
    file: UploadFile = File(...),
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Replaces `delivery_date`'s Keells prices with the file's, in one
    transaction — or changes nothing if any row has a problem. The file is
    re-checked here, not trusted from the preview.
    """
    contents = await _read_keells_upload(file)
    return await run_in_threadpool(
        keells_import_service.import_keells_excel, db, admin, delivery_date, contents, file.filename
    )
