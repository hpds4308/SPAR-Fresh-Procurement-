"""
Supplier price submission.

Business rule (as agreed with the client): a supplier submits prices for
the products they can supply, before the daily cutoff (default 12:00,
Asia/Colombo), and those prices apply to delivery *two days later* — the
same lead time branch orders use (order_service.py), so a submission
made today lines up with orders placed today for the same future
delivery date. Pricing's delivery_date is deliberately NOT the same as
the submission date here.

Resubmitting a price for the same product/delivery date before the cutoff
overwrites the previous quote (upsert), so a supplier can correct a typo
or adjust before the window closes without creating duplicate rows.
"""
import io
import math
import re
import zipfile
from datetime import datetime, date, timedelta, time, timezone
from zoneinfo import ZoneInfo

import openpyxl
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError, PermissionDeniedError, NotFoundError
from app.models.pricing import SupplierPrice
from app.models.market_reference_price import MarketReferencePrice
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.pricing import PriceSubmitRequest, PriceWindowOut
from app.services import settings_service

BUSINESS_TZ = ZoneInfo("Asia/Colombo")

# Business rule (as agreed with the client): suppliers only submit prices on
# Monday, Wednesday and Friday — date.weekday() has Monday=0 .. Sunday=6.
SUBMISSION_WEEKDAYS = {0, 2, 4}
SUBMISSION_DAYS_LABEL = "Monday, Wednesday and Friday"


def _parse_cutoff(cutoff_str: str) -> time:
    hh, mm = cutoff_str.split(":")
    return time(hour=int(hh), minute=int(mm))


def _most_recent_submission_date(on_date: date) -> date:
    """The most recent Monday/Wednesday/Friday on or before `on_date` — the
    submission day whose prices are still the current ones to show. Walking
    back at most 2 days always lands on a submission weekday."""
    d = on_date
    while d.weekday() not in SUBMISSION_WEEKDAYS:
        d -= timedelta(days=1)
    return d


def _current_cycle_delivery_date(now: datetime) -> date:
    """
    The delivery date tied to the most recently opened submission cycle —
    e.g. on a Tuesday this is still Monday's delivery date (Monday + 2),
    not today + 2, because Monday's submission is the latest set of prices
    suppliers have actually given. Unlike get_price_window's `delivery_date`
    (always today + 2, used for the supplier's own submission window), this
    is what Admin's browse views should default to so they land on the
    cycle that's actually live instead of a delivery date nothing has been
    submitted for yet.
    """
    submission_date = _most_recent_submission_date(now.date())
    return submission_date + timedelta(days=2)


def second_lowest_price(prices: list[float]) -> float | None:
    """
    The next DISTINCT price tier below the lowest of a set of supplier
    quotes, or None if fewer than two distinct prices exist yet. Ties at
    the lowest price don't count as a second tier — e.g. quotes of
    300/300/320 have a second-lowest of 320, not another 300. This is the
    conventional reading of "second-lowest bid" in procurement (the price
    a switch away from the cheapest would actually cost), but it's a real
    interpretation choice for ties, not something this codebase had
    already defined before — worth confirming against the actual business
    rule if a different tie-breaking convention was intended.
    """
    distinct_sorted = sorted(set(prices))
    return distinct_sorted[1] if len(distinct_sorted) >= 2 else None


def get_price_window(db: Session, now: datetime | None = None) -> PriceWindowOut:
    """Delivery date is always 2 days after the submission date — gives suppliers lead time."""
    now = now.astimezone(BUSINESS_TZ) if now else datetime.now(BUSINESS_TZ)
    cutoff_str = settings_service.get_setting(db, settings_service.SUPPLIER_PRICE_DEADLINE)
    is_open = now.weekday() in SUBMISSION_WEEKDAYS and now.time() < _parse_cutoff(cutoff_str)
    delivery_date = now.date() + timedelta(days=2)
    return PriceWindowOut(
        is_open=is_open,
        delivery_date=delivery_date,
        cutoff_time=cutoff_str,
        server_time=now.isoformat(),
        current_cycle_delivery_date=_current_cycle_delivery_date(now),
    )


def submit_prices(db: Session, supplier_user: User, payload: PriceSubmitRequest) -> list[SupplierPrice]:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can submit prices.")

    window = get_price_window(db)
    if not window.is_open:
        raise ValidationFailedError(
            f"Price submission for {window.delivery_date.isoformat()} is closed. "
            f"Suppliers can submit prices on {SUBMISSION_DAYS_LABEL} only, "
            f"before the daily cutoff of {window.cutoff_time}."
        )

    product_ids = [p.product_id for p in payload.prices]
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
    missing = set(product_ids) - set(products.keys())
    if missing:
        raise ValidationFailedError(f"Unknown product id(s): {sorted(missing)}")
    if len(product_ids) != len(set(product_ids)):
        raise ValidationFailedError("Each product can only appear once — combine duplicate entries.")

    units = {u.id: u.code for u in db.query(ProductUnit).all()}

    existing = {
        sp.product_id: sp
        for sp in db.query(SupplierPrice)
        .filter(
            SupplierPrice.supplier_id == supplier_user.supplier_id,
            SupplierPrice.delivery_date == window.delivery_date,
            SupplierPrice.product_id.in_(product_ids),
        )
        .all()
    }

    # Each submission is the supplier's complete price list for this delivery
    # date, not an incremental add — so any previously-submitted product left
    # out of this payload has been withdrawn and its stale quote must go too,
    # otherwise Admin keeps seeing a "live" price the supplier no longer offers.
    cleared_count = (
        db.query(SupplierPrice)
        .filter(
            SupplierPrice.supplier_id == supplier_user.supplier_id,
            SupplierPrice.delivery_date == window.delivery_date,
            SupplierPrice.product_id.notin_(product_ids),
        )
        .delete(synchronize_session=False)
    )

    saved: list[SupplierPrice] = []
    for entry in payload.prices:
        product = products[entry.product_id]
        if entry.product_id in existing:
            row = existing[entry.product_id]
            row.price = entry.price
            row.submitted_by = supplier_user.id
        else:
            row = SupplierPrice(
                supplier_id=supplier_user.supplier_id,
                product_id=entry.product_id,
                delivery_date=window.delivery_date,
                price=entry.price,
                unit_code=units.get(product.unit_id, "?"),
                submitted_by=supplier_user.id,
            )
            db.add(row)
        saved.append(row)

    try:
        db.commit()
    except IntegrityError:
        # Belt-and-braces, matching the same pattern in order_service: a
        # concurrent double-submit for the same supplier/product/date could
        # race past the upsert check above, so this catches the database's
        # own unique constraint instead of surfacing a raw 500.
        db.rollback()
        raise ValidationFailedError(
            "One or more of these prices were just submitted from another session. "
            "Please refresh and try again."
        )
    for row in saved:
        db.refresh(row)

    description = f"{len(payload.prices)} price(s) submitted for delivery {window.delivery_date.isoformat()}."
    if cleared_count:
        description += f" {cleared_count} previously-submitted price(s) not in this list were cleared."
    write_audit_log(
        db,
        user_id=supplier_user.id,
        role="SUPPLIER",
        action="PRICES_SUBMITTED",
        entity_type="supplier_price",
        entity_id=supplier_user.supplier_id,
        description=description,
    )
    return saved


def list_my_prices(db: Session, supplier_user: User, delivery_date: date | None = None) -> list[SupplierPrice]:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts have prices.")
    query = db.query(SupplierPrice).filter(SupplierPrice.supplier_id == supplier_user.supplier_id)
    if delivery_date:
        query = query.filter(SupplierPrice.delivery_date == delivery_date)
    else:
        window = get_price_window(db)
        query = query.filter(SupplierPrice.delivery_date == window.delivery_date)
    return query.order_by(SupplierPrice.product_id).all()


def get_last_prices(db: Session, supplier_user: User) -> list[SupplierPrice]:
    """
    For each product this supplier has ever quoted, their single most
    recent submission (by delivery_date, then id as a tiebreaker) —
    regardless of which delivery date it was for. Purely informational:
    shown on the Submit Prices page as a reference so a supplier can see
    what they last charged without it being pre-filled into this window's
    submission (that stays a deliberate, separate action).
    """
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts have prices.")
    rows = (
        db.query(SupplierPrice)
        .filter(SupplierPrice.supplier_id == supplier_user.supplier_id)
        .order_by(SupplierPrice.product_id, SupplierPrice.delivery_date.desc(), SupplierPrice.id.desc())
        .all()
    )
    latest_by_product: dict[int, SupplierPrice] = {}
    for row in rows:
        if row.product_id not in latest_by_product:
            latest_by_product[row.product_id] = row
    return list(latest_by_product.values())


def list_all_prices(
    db: Session,
    delivery_date: date | None = None,
    supplier_id: int | None = None,
    product_id: int | None = None,
):
    """
    Admin-only view: every supplier's quoted price across the whole
    catalogue for one delivery date, so Admin can browse and compare
    without going product-by-product. Defaults to the current submission
    cycle's delivery date (the most recent Mon/Wed/Fri submission's
    delivery date) when none is given.
    """
    if delivery_date is None:
        delivery_date = _current_cycle_delivery_date(datetime.now(BUSINESS_TZ))

    query = db.query(SupplierPrice).filter(SupplierPrice.delivery_date == delivery_date)
    if supplier_id:
        query = query.filter(SupplierPrice.supplier_id == supplier_id)
    if product_id:
        query = query.filter(SupplierPrice.product_id == product_id)
    rows = query.all()

    supplier_ids = {r.supplier_id for r in rows}
    product_ids = {r.product_id for r in rows}
    suppliers = {s.id: s for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(product_ids)).all()}
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}

    lowest_by_product: dict[int, float] = {}
    prices_by_product: dict[int, list[float]] = {}
    for r in rows:
        price = float(r.price)
        prices_by_product.setdefault(r.product_id, []).append(price)
        current = lowest_by_product.get(r.product_id)
        if current is None or price < current:
            lowest_by_product[r.product_id] = price

    second_lowest_by_product = {pid: second_lowest_price(prices) for pid, prices in prices_by_product.items()}

    result = []
    for r in rows:
        supplier = suppliers.get(r.supplier_id)
        product = products.get(r.product_id)
        price = float(r.price)
        second_lowest = second_lowest_by_product.get(r.product_id)
        result.append(
            {
                "id": r.id,
                "supplier_id": r.supplier_id,
                "supplier_code": supplier.supplier_code if supplier else "—",
                "supplier_name": supplier.supplier_name if supplier else "—",
                "product_id": r.product_id,
                "product_code": product.product_code if product else "—",
                "product_description": product.description if product else "—",
                "category_name": categories.get(product.category_id, "—") if product else "—",
                "unit_code": r.unit_code,
                "price": price,
                "adjusted_price": float(r.adjusted_price) if r.adjusted_price is not None else None,
                "sent_to_supplier": r.sent_to_supplier_at is not None,
                "delivery_date": r.delivery_date,
                "is_lowest_for_product": price == lowest_by_product.get(r.product_id),
                "second_lowest_price": second_lowest,
                "is_second_lowest_for_product": second_lowest is not None and price == second_lowest,
            }
        )
    # Fixed display grouping: Fruit, Vege Low, Vege Pola, Vege Up (category
    # IDs 1-4 already match that order), alphabetical by item within each.
    category_display_order = {"Fruit": 0, "Vege Low": 1, "Vege Pola": 2, "Vege Up": 3}
    result.sort(
        key=lambda row: (
            category_display_order.get(row["category_name"], len(category_display_order)),
            row["product_description"],
            row["price"],
        )
    )
    return result


def set_adjusted_price(db: Session, admin: User, price_id: int, adjusted_price: float | None) -> SupplierPrice:
    """
    Admin sets (or clears, with None) their negotiated price for one
    supplier's quote. The supplier's original `price` is left untouched —
    this only ever writes to `adjusted_price`. This is a draft: it does
    NOT reach the supplier until Admin calls send_adjusted_price below, so
    any prior "sent" state is cleared whenever the value changes.
    """
    row = db.query(SupplierPrice).filter(SupplierPrice.id == price_id).first()
    if not row:
        raise NotFoundError("That supplier price quote was not found.")

    row.adjusted_price = adjusted_price
    row.adjusted_by = admin.id if adjusted_price is not None else None
    row.adjusted_at = datetime.now(BUSINESS_TZ) if adjusted_price is not None else None
    row.sent_to_supplier_at = None  # any edit un-sends it — supplier must be sent the new value explicitly
    db.commit()
    db.refresh(row)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="SUPPLIER_PRICE_ADJUSTED",
        entity_type="supplier_price",
        entity_id=row.id,
        description=(
            f"Adjusted price set to {adjusted_price} for supplier price #{row.id}."
            if adjusted_price is not None
            else f"Adjusted price cleared for supplier price #{row.id}."
        ),
    )
    return row


def send_adjusted_price(db: Session, admin: User, price_id: int) -> SupplierPrice:
    """
    Marks the current adjusted_price as sent — this is what makes it show
    up on the supplier's own price view. Requires a draft adjusted_price
    to already be set.
    """
    row = db.query(SupplierPrice).filter(SupplierPrice.id == price_id).first()
    if not row:
        raise NotFoundError("That supplier price quote was not found.")
    if row.adjusted_price is None:
        raise ValidationFailedError("Set an adjusted price before sending it to the supplier.")

    row.sent_to_supplier_at = datetime.now(BUSINESS_TZ)
    db.commit()
    db.refresh(row)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="SUPPLIER_PRICE_SENT",
        entity_type="supplier_price",
        entity_id=row.id,
        description=f"Adjusted price {row.adjusted_price} sent to supplier for supplier price #{row.id}.",
    )
    return row


def unsend_adjusted_price(db: Session, admin: User, price_id: int) -> SupplierPrice:
    """Withdraws a sent adjusted price so the supplier no longer sees it (adjusted_price stays as a draft)."""
    row = db.query(SupplierPrice).filter(SupplierPrice.id == price_id).first()
    if not row:
        raise NotFoundError("That supplier price quote was not found.")

    row.sent_to_supplier_at = None
    db.commit()
    db.refresh(row)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="SUPPLIER_PRICE_UNSENT",
        entity_type="supplier_price",
        entity_id=row.id,
        description=f"Adjusted price withdrawn from supplier view for supplier price #{row.id}.",
    )
    return row


# ---- Market reference prices (e.g. Keells retail price, entered by hand;
# or the LOCAL_MARKET wholesale prices from the daily auto-import — see
# harti_import_service.py) — purely informational, never used in any
# calculation elsewhere. ----


def list_reference_prices(
    db: Session, delivery_date: date, source: str = "KEELLS"
) -> list[MarketReferencePrice]:
    return (
        db.query(MarketReferencePrice)
        .filter(MarketReferencePrice.delivery_date == delivery_date, MarketReferencePrice.source == source)
        .all()
    )


def get_last_reference_prices(db: Session, source: str = "KEELLS") -> list[MarketReferencePrice]:
    """
    For each product, the single most recent reference price ever entered
    for it (any date), so a blank date can be pre-filled with "probably
    still this" instead of admin retyping the same number every window.
    Purely a UI convenience — never auto-written to the new date unless
    Admin actually interacts with that field.
    """
    rows = (
        db.query(MarketReferencePrice)
        .filter(MarketReferencePrice.source == source)
        .order_by(MarketReferencePrice.product_id, MarketReferencePrice.delivery_date.desc(), MarketReferencePrice.id.desc())
        .all()
    )
    latest_by_product: dict[int, MarketReferencePrice] = {}
    for row in rows:
        if row.product_id not in latest_by_product:
            latest_by_product[row.product_id] = row
    return list(latest_by_product.values())


def list_reference_price_history(
    db: Session, source: str, start_date: date, end_date: date
) -> list[MarketReferencePrice]:
    """Every reference price entry for one source across a date range — powers the
    admin-facing trend/history view (Product x Date), as opposed to list_reference_prices'
    single-date lookup used by the daily entry page."""
    return (
        db.query(MarketReferencePrice)
        .filter(
            MarketReferencePrice.source == source,
            MarketReferencePrice.delivery_date >= start_date,
            MarketReferencePrice.delivery_date <= end_date,
        )
        .all()
    )


def set_reference_price(
    db: Session,
    admin: User,
    product_id: int,
    delivery_date: date,
    price: float | None,
    source: str = "KEELLS",
) -> MarketReferencePrice | None:
    """Upserts (or, with price=None, deletes) the reference price for one product/date/source."""
    row = (
        db.query(MarketReferencePrice)
        .filter(
            MarketReferencePrice.product_id == product_id,
            MarketReferencePrice.source == source,
            MarketReferencePrice.delivery_date == delivery_date,
        )
        .first()
    )

    if price is None:
        if row:
            db.delete(row)
            db.commit()
        return None

    if row:
        row.price = price
        row.updated_by = admin.id
        row.updated_at = datetime.now(timezone.utc)
    else:
        row = MarketReferencePrice(
            product_id=product_id,
            source=source,
            delivery_date=delivery_date,
            price=price,
            updated_by=admin.id,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---- Keells reference price bulk import from an uploaded spreadsheet —
# a separate, admin-triggered alternative to typing each price by hand on
# AdminKeellsPrices.tsx. The spreadsheet is produced by an external
# Playwright scraper (not part of this app) with columns "DC Code",
# "System Name", "Keells Product Name", "Price", "Numeric Price"; only
# "DC Code" (matched exactly against Product.product_code — confirmed to
# use the same numeric scheme as database/seed/products.csv) and
# "Numeric Price" (falling back to parsing "Price", e.g. "Rs 350.00/KG",
# if the numeric column is blank) are actually used. Every matched row is
# upserted through the same set_reference_price used by manual entry, so
# behavior (upsert semantics, source="KEELLS") is identical either way. ----

_KEELLS_EXCEL_COLUMN_ALIASES = {
    "dc code": "dc_code",
    "system name": "system_name",
    "numeric price": "numeric_price",
    "price": "price",
}
_KEELLS_EXCEL_REQUIRED_COLUMNS = {"dc_code"}

# The real file is ~60 rows (see scraper.js's requiredProducts list) — these
# limits are generous for that but still small enough to reject an abusive
# upload before it's fully parsed, the same reasoning as order_service.py's
# _reject_oversized_workbook/MAX_EXCEL_ROWS_SCANNED for the order template.
MAX_KEELLS_EXCEL_UNCOMPRESSED_BYTES = 2 * 1024 * 1024
MAX_KEELLS_EXCEL_ROWS_SCANNED = 5_000
MAX_KEELLS_EXCEL_ROWS = 1_000
_KEELLS_EXCEL_TOO_BIG_MESSAGE = "This file is too large or has too many rows — please upload the scraper's output file as-is, unmodified."
_KEELLS_PRICE_RE = re.compile(r"([\d,]+(?:\.\d+)?)")


def _reject_oversized_keells_workbook(file_bytes: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            unpacked = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        return  # not a zip at all - the normal "could not read this file" error below covers it
    if unpacked > MAX_KEELLS_EXCEL_UNCOMPRESSED_BYTES:
        raise ValidationFailedError(_KEELLS_EXCEL_TOO_BIG_MESSAGE)


def _parse_keells_dc_code(raw) -> str | None:
    if raw is None:
        return None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)  # Excel sometimes stores a numeric-looking code as a float (4503253.0)
    code = str(raw).strip()
    return code or None


def _parse_keells_price(values: dict) -> float | None:
    numeric = values.get("numeric_price")
    if isinstance(numeric, (int, float)) and not isinstance(numeric, bool) and math.isfinite(numeric) and numeric > 0:
        return round(float(numeric), 2)
    text = values.get("price")
    if text is None:
        return None
    m = _KEELLS_PRICE_RE.search(str(text))
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    return round(value, 2) if value > 0 else None


def import_keells_prices(db: Session, admin: User, delivery_date: date, file_bytes: bytes) -> dict:
    """
    Parses the uploaded Keells scraper spreadsheet and upserts a KEELLS
    reference price for every row whose DC Code matches a known product,
    for the given delivery_date. Returns a summary the admin UI shows
    (matched/saved counts and any DC codes it couldn't match), and never
    raises for individual bad rows — only for a file that can't be read
    at all or is too large, mirroring order_service.parse_order_excel.
    """
    _reject_oversized_keells_workbook(file_bytes)

    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        sheet = workbook.active
        rows = sheet.iter_rows(values_only=True)
        header_row = next(rows)
    except Exception:
        raise ValidationFailedError(
            "Could not read this file — make sure it's the .xlsx file produced by the Keells scraper."
        )

    header_map: dict[int, str] = {}
    for idx, cell in enumerate(header_row):
        key = _KEELLS_EXCEL_COLUMN_ALIASES.get(str(cell).strip().lower()) if cell is not None else None
        if key:
            header_map[idx] = key

    missing = _KEELLS_EXCEL_REQUIRED_COLUMNS - set(header_map.values())
    if missing:
        raise ValidationFailedError(
            f"Missing required column(s): {', '.join(sorted(missing))}. Expected a header row with at least "
            "DC Code and Numeric Price (or Price)."
        )
    if "numeric_price" not in header_map.values() and "price" not in header_map.values():
        raise ValidationFailedError("Expected a 'Numeric Price' or 'Price' column with the Keells prices in it.")

    products_by_code = {p.product_code: p for p in db.query(Product).all()}

    matched = 0
    saved = 0
    skipped_rows = 0
    seen_codes: set[str] = set()
    unmatched: list[dict] = []
    for row_number, raw_row in enumerate(rows, start=2):  # row 1 is the header
        if row_number - 1 > MAX_KEELLS_EXCEL_ROWS_SCANNED:
            raise ValidationFailedError(_KEELLS_EXCEL_TOO_BIG_MESSAGE)
        values = {header_map[i]: raw_row[i] for i in range(len(raw_row)) if i in header_map}

        dc_code = _parse_keells_dc_code(values.get("dc_code"))
        if not dc_code:
            continue  # blank trailing row, silently skipped like order_service does

        if len(seen_codes) >= MAX_KEELLS_EXCEL_ROWS:
            raise ValidationFailedError(_KEELLS_EXCEL_TOO_BIG_MESSAGE)
        if dc_code in seen_codes:
            skipped_rows += 1
            continue
        seen_codes.add(dc_code)

        price = _parse_keells_price(values)
        if price is None:
            skipped_rows += 1
            continue
        matched += 1

        product = products_by_code.get(dc_code)
        if not product:
            system_name = values.get("system_name")
            unmatched.append({"dc_code": dc_code, "system_name": str(system_name).strip() if system_name else None})
            continue

        set_reference_price(db, admin, product.id, delivery_date, price, "KEELLS")
        saved += 1

    return {
        "delivery_date": delivery_date,
        "matched": matched,
        "saved": saved,
        "skipped_rows": skipped_rows,
        "unmatched": unmatched,
    }
