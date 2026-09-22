from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ValidationFailedError
from app.core.security import get_current_user, require_roles
from app.models.product import Product
from app.models.user import User
from app.schemas.pricing import (
    PriceSubmitRequest,
    SupplierPriceOut,
    PriceWindowOut,
    AdminSupplierPriceOut,
    AdjustPriceRequest,
    LastPriceOut,
    KeellsImportResultOut,
    ReferencePriceOut,
    ReferencePriceSetRequest,
)
from app.services import pricing_service

router = APIRouter(prefix="/pricing", dependencies=[Depends(get_current_user)])


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
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_([r.product_id for r in rows])).all()}
    return [
        SupplierPriceOut(
            id=r.id,
            product_id=r.product_id,
            product_code=products[r.product_id].product_code,
            product_description=products[r.product_id].description,
            unit_code=r.unit_code,
            price=float(r.price),
            delivery_date=r.delivery_date,
            adjusted_price=float(r.adjusted_price) if r.sent_to_supplier_at and r.adjusted_price is not None else None,
        )
        for r in rows
    ]


@router.get("/mine", response_model=list[SupplierPriceOut])
def my_prices(
    delivery_date: date | None = None,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    rows = pricing_service.list_my_prices(db, current_user, delivery_date)
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_([r.product_id for r in rows])).all()}
    return [
        SupplierPriceOut(
            id=r.id,
            product_id=r.product_id,
            product_code=products[r.product_id].product_code,
            product_description=products[r.product_id].description,
            unit_code=r.unit_code,
            price=float(r.price),
            delivery_date=r.delivery_date,
            adjusted_price=float(r.adjusted_price) if r.sent_to_supplier_at and r.adjusted_price is not None else None,
        )
        for r in rows
    ]


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
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Every supplier's quoted price across the whole catalogue for one
    delivery date — the admin's browse/compare view, as opposed to
    /orders/admin/product/{id}/comparison which looks at one product at a time.
    """
    rows = pricing_service.list_all_prices(db, delivery_date, supplier_id, product_id)
    return [AdminSupplierPriceOut(**row) for row in rows]


@router.patch("/admin/{price_id}/adjust")
def admin_adjust_price(
    price_id: int,
    payload: AdjustPriceRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Set (or clear, with adjusted_price: null) Admin's negotiated price for one supplier quote."""
    row = pricing_service.set_adjusted_price(db, admin, price_id, payload.adjusted_price)
    return {
        "id": row.id,
        "price": float(row.price),
        "adjusted_price": float(row.adjusted_price) if row.adjusted_price is not None else None,
        "sent_to_supplier": row.sent_to_supplier_at is not None,
    }


@router.post("/admin/{price_id}/send")
def admin_send_price(
    price_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Sends the current adjusted price to the supplier — it becomes visible on their price view."""
    row = pricing_service.send_adjusted_price(db, admin, price_id)
    return {
        "id": row.id,
        "adjusted_price": float(row.adjusted_price) if row.adjusted_price is not None else None,
        "sent_to_supplier": row.sent_to_supplier_at is not None,
    }


@router.post("/admin/{price_id}/unsend")
def admin_unsend_price(
    price_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Withdraws a sent adjusted price so the supplier no longer sees it."""
    row = pricing_service.unsend_adjusted_price(db, admin, price_id)
    return {
        "id": row.id,
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


# Generous ceiling for the Keells import spreadsheet — the real file is a
# few hundred KB for ~60 rows; this only rejects something clearly wrong,
# same reasoning as MAX_ORDER_EXCEL_BYTES in orders.py.
MAX_KEELLS_EXCEL_BYTES = 2 * 1024 * 1024


@router.post("/reference/keells-import", response_model=KeellsImportResultOut)
async def import_keells_prices(
    delivery_date: date,
    file: UploadFile = File(...),
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Bulk-imports KEELLS reference prices from the .xlsx produced by the
    external Keells scraper (DC Code + Numeric Price columns), upserting
    into the same market_reference_prices table manual entry on
    AdminKeellsPrices.tsx uses. Never touches any other price source.
    """
    contents = await file.read(MAX_KEELLS_EXCEL_BYTES + 1)
    if len(contents) > MAX_KEELLS_EXCEL_BYTES:
        raise ValidationFailedError("That file is too large — please upload the scraper's output file as-is.")
    return await run_in_threadpool(pricing_service.import_keells_prices, db, admin, delivery_date, contents)
