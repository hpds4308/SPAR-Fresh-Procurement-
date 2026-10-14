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
from datetime import datetime, date, timedelta, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError, PermissionDeniedError, NotFoundError
from app.models.pricing import SupplierPrice
from app.models.market_reference_price import MarketReferencePrice
from app.models.product import Product, ProductCategory, ProductUnit
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas._limits import MAX_NUMERIC_10_2
from app.schemas.pricing import (
    ExcelPriceLinePreview,
    ExcelPricePreviewOut,
    PriceSubmitRequest,
    PriceWindowOut,
)
from app.services import settings_service
from app.services import price_approval_service

BUSINESS_TZ = ZoneInfo("Asia/Colombo")


def get_submission_weekdays(db: Session) -> list[int]:
    """The weekdays suppliers may submit prices on (date.weekday(): Monday=0
    .. Sunday=6) — Admin-chosen on the Settings page, Monday/Wednesday/Friday
    until changed there."""
    return settings_service.parse_weekdays(
        settings_service.get_setting(db, settings_service.SUPPLIER_PRICE_DAYS)
    )


def _parse_cutoff(cutoff_str: str) -> time:
    hh, mm = cutoff_str.split(":")
    return time(hour=int(hh), minute=int(mm))


def _most_recent_submission_date(on_date: date, weekdays: list[int]) -> date:
    """The most recent submission weekday on or before `on_date` — the
    submission day whose prices are still the current ones to show. Walking
    back at most 6 days always lands on one, since at least one is set."""
    d = on_date
    while d.weekday() not in weekdays:
        d -= timedelta(days=1)
    return d


def _current_cycle_delivery_date(now: datetime, weekdays: list[int]) -> date:
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
    submission_date = _most_recent_submission_date(now.date(), weekdays)
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
    weekdays = get_submission_weekdays(db)
    is_open = now.weekday() in weekdays and now.time() < _parse_cutoff(cutoff_str)
    delivery_date = now.date() + timedelta(days=2)
    return PriceWindowOut(
        is_open=is_open,
        delivery_date=delivery_date,
        cutoff_time=cutoff_str,
        server_time=now.isoformat(),
        current_cycle_delivery_date=_current_cycle_delivery_date(now, weekdays),
        submission_days=weekdays,
        submission_days_label=settings_service.weekdays_label(weekdays),
    )


def submit_prices(db: Session, supplier_user: User, payload: PriceSubmitRequest) -> list[SupplierPrice]:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can submit prices.")

    window = get_price_window(db)
    if not window.is_open:
        raise ValidationFailedError(
            f"Price submission for {window.delivery_date.isoformat()} is closed. "
            f"Suppliers can submit prices on {window.submission_days_label} only, "
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

    # Any price sheet still waiting for this supplier's signature was built
    # on the quotes being replaced now, so it's voided (see
    # price_approval_service) — Admin re-sends once they've reviewed.
    voided_sheets = price_approval_service.on_supplier_resubmitted(
        db, supplier_user.supplier_id, window.delivery_date
    )

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
    if voided_sheets:
        description += f" {voided_sheets} price sheet(s) waiting for approval were voided."
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


# ---- Excel price upload — an alternate way for a supplier to fill in
# their prices: download the template (every active product), fill in the
# Price column, upload it back. ----

EXCEL_PRICE_HEADERS = ("Product Code", "Category", "Product", "Price")
_EXCEL_PRICE_ALIASES = {
    "product code": "product_code",
    "code": "product_code",
    "item code": "product_code",
    "product": "description",
    "product name": "description",
    "product description": "description",
    "description": "description",
    "price": "price",
    "price (rs.)": "price",
    "price (rs)": "price",
    "price rs": "price",
    "unit price": "price",
}
_EXCEL_PRICE_REQUIRED = {"product_code", "price"}
# The template has a logo and title above the header, and a supplier may
# add lines of their own; look this far down for it.
_EXCEL_HEADER_SEARCH_ROWS = 30
_SPAR_LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "spar-logo.png"
_SPAR_GREEN = "157946"
_EXCEL_ERROR_VALUES = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!", "#SPILL!", "#CALC!", "#GETTING_DATA"}


def build_price_template(db: Session) -> bytes:
    """
    The blank price sheet a supplier downloads: SPAR logo and title, then
    one row per active product in the same order as the Submit Prices page
    (category, then name). Deliberately left unprotected and without data
    validation: suppliers fill the Price column with VLOOKUPs against their
    own price lists, which needs helper columns, pasted data, and formulas
    that return #N/A for products they don't carry.
    """
    import io

    from openpyxl import Workbook
    from openpyxl.drawing.image import Image as XLImage
    from openpyxl.styles import Alignment, Font, PatternFill

    products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE")
        .order_by(Product.category_id, Product.description)
        .all()
    )
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}

    wb = Workbook()
    ws = wb.active
    ws.title = "Prices"
    last_col = len(EXCEL_PRICE_HEADERS)

    # Rows 1-3: logo, title, instructions. The upload parser finds the
    # header row below them by its column names.
    ws.row_dimensions[1].height = 42
    logo = XLImage(str(_SPAR_LOGO_PATH))
    logo.width, logo.height = 280, 44  # source is 1014x161
    ws.add_image(logo, "A1")

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws["A2"] = "Supplier Price List — Fruits & Vegetables"
    ws["A2"].font = Font(bold=True, size=14, color=_SPAR_GREEN)
    ws.row_dimensions[2].height = 22

    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_col)
    ws["A3"] = (
        "Enter your price in Rs. in the yellow Price column. Leave it blank for products you don't supply. "
        "Don't change the product codes."
    )
    ws["A3"].font = Font(italic=True, size=9, color="666666")
    ws["A3"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[3].height = 26

    header_row = 4
    for col, title in enumerate(EXCEL_PRICE_HEADERS, start=1):
        cell = ws.cell(row=header_row, column=col, value=title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color=_SPAR_GREEN, end_color=_SPAR_GREEN, fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    price_fill = PatternFill(start_color="FFF9E6", end_color="FFF9E6", fill_type="solid")
    for p in products:
        # All-digit codes go in as numbers so a VLOOKUP against a supplier's
        # own sheet (where codes are almost always typed as numbers) matches;
        # a code with a leading zero or letters has to stay text.
        code = int(p.product_code) if p.product_code.isdigit() and not p.product_code.startswith("0") else p.product_code
        ws.append([code, categories.get(p.category_id, ""), p.description, None])
        ws.cell(row=ws.max_row, column=1).number_format = "0" if isinstance(code, int) else "@"
        price_cell = ws.cell(row=ws.max_row, column=last_col)
        price_cell.fill = price_fill
        price_cell.number_format = "#,##0.00"

    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 40
    ws.column_dimensions["D"].width = 14
    ws.freeze_panes = f"A{header_row + 1}"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _parse_excel_price(raw) -> tuple[float | None, str | None]:
    """Blank is (None, None) — the supplier isn't quoting that product.
    Accepts plain numbers and text like "Rs. 1,250.00". An Excel error value
    (#N/A from a VLOOKUP that found nothing, etc.) also counts as blank."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None, None
    if isinstance(raw, str) and raw.strip().upper() in _EXCEL_ERROR_VALUES:
        return None, None
    if isinstance(raw, bool):
        return None, f"'{raw}' is not a valid price."
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        text = str(raw).strip().lower().replace(",", "").replace("rs.", "").replace("rs", "").strip()
        try:
            value = float(text)
        except ValueError:
            return None, f"'{raw}' is not a valid price."
    if value <= 0:
        return None, "Price must be greater than zero (leave it blank if you don't supply this product)."
    if value > MAX_NUMERIC_10_2:
        return None, f"Price exceeds the maximum allowed value ({MAX_NUMERIC_10_2:,.2f})."
    return round(value, 2), None


def _price_header_key(cell) -> str | None:
    """Which template column a heading means. Exact names first, then a
    forgiving match ("Price (LKR)", "Item Code", "Rate") because suppliers
    rename headings; a POS code column is never mistaken for the product code."""
    if cell is None:
        return None
    text = " ".join(str(cell).strip().lower().replace("*", "").replace(":", "").split())
    if not text:
        return None
    if text in _EXCEL_PRICE_ALIASES:
        return _EXCEL_PRICE_ALIASES[text]
    if "pos" in text.split():
        return None
    if "code" in text:
        return "product_code"
    if "price" in text or "rate" in text:
        return "price"
    if "product" in text or "description" in text or "item" in text:
        return "description"
    return None


def _price_sheets(file_bytes: bytes):
    """Yields each sheet of the upload as an iterator of row tuples, the
    template's "Prices" sheet first. Also takes a CSV; an old .xls gets a
    clear message instead of a generic read failure."""
    import csv
    import io

    import openpyxl

    if file_bytes[:4] == bytes.fromhex("d0cf11e0"):
        raise ValidationFailedError(
            "This is an old Excel 97-2003 (.xls) file. Open it in Excel, choose File > Save As > "
            "Excel Workbook (.xlsx), and upload that copy."
        )
    if file_bytes[:2] != b"PK":
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1")
        rows = list(csv.reader(io.StringIO(text)))
        if not rows:
            raise ValidationFailedError("This file is empty.")
        yield iter([tuple(r) for r in rows])
        return

    workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    # Suppliers often add a sheet of their own prices to VLOOKUP from and
    # save with that sheet open, so the active sheet isn't necessarily ours.
    active_title = workbook.active.title if workbook.active is not None else None
    for sheet in sorted(workbook.worksheets, key=lambda ws: (ws.title != "Prices", ws.title != active_title)):
        sheet.reset_dimensions()  # some non-Excel tools write a wrong size; read every row that's there
        yield sheet.iter_rows(values_only=True)


def parse_price_excel(db: Session, supplier_user: User, file_bytes: bytes) -> ExcelPricePreviewOut:
    """
    Parses an uploaded price Excel into a row-by-row preview — never saves
    anything. The supplier confirms the preview and the valid rows are then
    submitted through submit_prices like manual entry, so the submission
    window and cutoff are enforced exactly the same way.
    """
    from app.services.order_service import (
        MAX_EXCEL_ROWS_SCANNED,
        _reject_oversized_workbook,
    )

    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can upload prices.")

    too_big = "This file is too large or has too many rows — please upload the price template as-is."
    try:
        _reject_oversized_workbook(file_bytes)
    except ValidationFailedError:
        raise ValidationFailedError(too_big)

    header_map: dict[int, str] = {}
    header_row_number = 0
    rows = iter(())
    # The heading row that came closest, quoted back if no header is found.
    seen_headers: list[str] = []
    best_match = -1
    try:
        for sheet_rows in _price_sheets(file_bytes):
            rows = sheet_rows
            for header_row_number, row in enumerate(rows, start=1):
                candidate: dict[int, str] = {}
                for idx, cell in enumerate(row):
                    key = _price_header_key(cell)
                    if key and key not in candidate.values():
                        candidate[idx] = key
                if _EXCEL_PRICE_REQUIRED <= set(candidate.values()):
                    header_map = candidate
                    break
                headings = [str(c).strip() for c in row if c is not None and str(c).strip()]
                if headings and len(candidate) > best_match:
                    best_match, seen_headers = len(candidate), headings
                if header_row_number >= _EXCEL_HEADER_SEARCH_ROWS:
                    break
            if header_map:
                break
    except ValidationFailedError:
        raise
    except Exception:
        raise ValidationFailedError(
            "Could not read this file. Open it in Excel, choose File > Save As > Excel Workbook (.xlsx), "
            "and upload that copy."
        )

    if not header_map:
        found = f" Found these headings: {', '.join(seen_headers[:8])}." if seen_headers else ""
        raise ValidationFailedError(
            "Could not find the Product Code and Price columns — keep the template's heading row "
            "(Product Code, Category, Product, Price) as it is and put your prices under Price." + found
        )

    products_by_code = {p.product_code: p for p in db.query(Product).filter(Product.status == "ACTIVE").all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}

    lines: list[ExcelPriceLinePreview] = []
    blank_price_count = 0
    seen_codes: set[str] = set()
    try:
        for row_number, raw_row in enumerate(rows, start=header_row_number + 1):
            if row_number > MAX_EXCEL_ROWS_SCANNED:
                raise ValidationFailedError(too_big)
            values = {header_map[i]: raw_row[i] for i in range(len(raw_row)) if i in header_map}
            raw_code = values.get("product_code")
            # A whole-number code typed into a General cell comes back as a float (1001.0).
            if isinstance(raw_code, float) and raw_code.is_integer():
                raw_code = int(raw_code)
            product_code = str(raw_code or "").strip()
            if product_code.endswith(".0") and product_code[:-2].isdigit():
                product_code = product_code[:-2]
            if not product_code:
                continue  # blank trailing row
            description = str(values["description"]).strip() if values.get("description") is not None else None

            price, price_error = _parse_excel_price(values.get("price"))
            if price is None and price_error is None:
                blank_price_count += 1
                continue

            line = ExcelPriceLinePreview(
                row_number=row_number, product_code=product_code, description=description, price=price
            )
            product = products_by_code.get(product_code)
            if product_code in seen_codes:
                line.error = "Duplicate product code — already appears earlier in this file."
            elif not product:
                line.error = "Unknown or inactive product code."
            elif price_error:
                line.error = price_error
                line.description = product.description
                line.unit_code = units.get(product.unit_id)
            else:
                line.product_id = product.id
                line.description = product.description
                line.unit_code = units.get(product.unit_id)
            seen_codes.add(product_code)
            lines.append(line)
    except ValidationFailedError:
        raise
    except Exception:
        raise ValidationFailedError("Could not read this file — make sure it's a valid .xlsx file.")

    valid = sum(1 for line in lines if line.error is None)
    return ExcelPricePreviewOut(
        lines=lines,
        valid_line_count=valid,
        error_count=len(lines) - valid,
        blank_price_count=blank_price_count,
    )


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
    statuses = price_approval_service.row_statuses(db, rows)

    result = []
    for r in rows:
        supplier = suppliers.get(r.supplier_id)
        product = products.get(r.product_id)
        price = float(r.price)
        second_lowest = second_lowest_by_product.get(r.product_id)
        approval_status, revision, counter_price = statuses[r.id]
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
                "approval_status": approval_status,
                "revision_id": revision.id if revision else None,
                "rejection_reason": revision.rejection_reason if revision and approval_status == "REJECTED" else None,
                "counter_price": counter_price,
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
    NOT reach the supplier until Admin sends it for approval (see
    price_approval_service.send_for_approval). If it was already on a
    price sheet — waiting or even approved — that whole sheet is voided,
    so the supplier is never held to a figure they didn't sign for.
    """
    row = db.query(SupplierPrice).filter(SupplierPrice.id == price_id).first()
    if not row:
        raise NotFoundError("That supplier price quote was not found.")

    current = float(row.adjusted_price) if row.adjusted_price is not None else None
    if current == adjusted_price:
        return row

    voided = price_approval_service.on_adjusted_price_changed(db, row)
    row.adjusted_price = adjusted_price
    row.adjusted_by = admin.id if adjusted_price is not None else None
    row.adjusted_at = datetime.now(BUSINESS_TZ) if adjusted_price is not None else None
    db.commit()
    db.refresh(row)

    description = (
        f"Adjusted price set to {adjusted_price} for supplier price #{row.id}."
        if adjusted_price is not None
        else f"Adjusted price cleared for supplier price #{row.id}."
    )
    if voided:
        description += f" Price sheet #{voided.id} voided — it must be sent and signed again."
    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="SUPPLIER_PRICE_ADJUSTED",
        entity_type="supplier_price",
        entity_id=row.id,
        description=description,
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


def clear_reference_prices(db: Session, delivery_date: date, source: str = "KEELLS") -> int:
    """
    Deletes every reference price row for one source/date. Used by
    keells_scrape_service.run_scrape to fully REPLACE a day's KEELLS
    prices with a fresh scrape rather than merging on top of whatever was
    there before (the Keells Price page is sync-only now — see
    AdminKeellsPrices.tsx — so nothing should be left over from a manual
    entry or a stale prior scrape once a new one has run). Returns the
    number of rows removed.
    """
    deleted = (
        db.query(MarketReferencePrice)
        .filter(MarketReferencePrice.delivery_date == delivery_date, MarketReferencePrice.source == source)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted
