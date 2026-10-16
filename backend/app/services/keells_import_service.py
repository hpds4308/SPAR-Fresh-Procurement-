"""
Keells retail prices from an uploaded Excel file — the supported way to
update them while keellssuper.com blocks the server-side sync (see
keells_scrape_service.py). The file is the one the standalone Keells
scraper writes on an office PC ("keells-required-products.xlsx", sheet
"Required Products"): DC Code, System Name, Keells Product Name, Category,
Price ("Rs 1,650.00 /  KG"), Unit, Numeric Price, Scraped At.

Two steps, both re-reading the file so nothing is trusted from the browser:
1. preview_keells_excel — validates every row, saves nothing.
2. import_keells_excel — all-or-nothing: if ANY row has a problem nothing
   is written; otherwise the chosen date's KEELLS prices are replaced in
   one transaction (pricing_service.replace_reference_prices), the same
   replace the sync does. Other dates and sources are never touched.

Rows are matched by DC Code (Product.product_code), and only for the
products on the established Keells comparison list
(keells_scrape_service.REQUIRED_PRODUCTS) — so e.g. PAPAYA TANNING, which
Keells doesn't sell, can never pick up a price. System Name must agree with
that product, which catches a row pasted against the wrong code.
"""
import io
import logging
import math
import re
import zipfile
from datetime import date

from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError
from app.models.market_reference_price import MarketReferencePrice
from app.models.product import Product
from app.models.user import User
from app.schemas._limits import MAX_NUMERIC_10_2
from app.services import pricing_service
from app.services.keells_scrape_service import REQUIRED_PRODUCTS, SOURCE

logger = logging.getLogger("spar.keells")

# Heading (lower-cased, spaces collapsed) -> field. Keells Product Name,
# Category and Scraped At are shown for context only.
_HEADERS = {
    "dc code": "dc_code",
    "system name": "system_name",
    "keells product name": "keells_name",
    "category": "category",
    "price": "price_text",
    "unit": "unit",
    "numeric price": "numeric_price",
    "scraped at": "scraped_at",
}
_REQUIRED_FIELDS = {"dc_code": "DC Code", "system_name": "System Name", "price_text": "Price", "unit": "Unit", "numeric_price": "Numeric Price"}
# The units keellssuper.com prices these products by.
_UNITS = {"KG": "KG", "UNIT": "Unit"}
_HEADER_SEARCH_ROWS = 10
MAX_ROWS_SCANNED = 2_000
MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
_TOO_BIG = "This file is too large or has too many rows — please upload the Keells price file as the scraper made it."
_EXCEL_ERRORS = {"#N/A", "#REF!", "#VALUE!", "#DIV/0!", "#NAME?", "#NULL!", "#NUM!"}
# "Rs 1,650.00 /  KG" -> 1650.00, "KG"
_PRICE_TEXT_RE = re.compile(r"^\s*(?:rs\.?)?\s*([\d,]+(?:\.\d+)?)\s*(?:/\s*(\w+))?\s*$", re.IGNORECASE)

_REQUIRED_BY_CODE = {p["dc_code"]: p["system_name"] for p in REQUIRED_PRODUCTS}


def _norm(text) -> str:
    return " ".join(str(text).replace("-", " ").replace("_", " ").upper().split())


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _dc_code(raw) -> str | None:
    if _blank(raw):
        return None
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)  # a numeric cell: 4503253.0
    return str(raw).strip()


def _number(raw) -> float | None:
    """A positive finite number from a numeric cell or numeric text, else None."""
    if isinstance(raw, bool) or _blank(raw):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
    else:
        try:
            value = float(str(raw).strip().replace(",", ""))
        except ValueError:
            return None
    return value if math.isfinite(value) else None


def _open_rows(file_bytes: bytes):
    """The data rows of the first sheet that has the expected header row,
    as (header_row_number, {field: column index}, rows iterator)."""
    import openpyxl

    if file_bytes[:4] == bytes.fromhex("d0cf11e0"):
        raise ValidationFailedError(
            "This is an old Excel 97-2003 (.xls) file. Open it in Excel, choose File > Save As > "
            "Excel Workbook (.xlsx), and upload that copy."
        )
    if file_bytes[:2] != b"PK":
        raise ValidationFailedError("This isn't an Excel (.xlsx) file. Upload the Keells price file the scraper made.")
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNCOMPRESSED_BYTES:
                raise ValidationFailedError(_TOO_BIG)
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except ValidationFailedError:
        raise
    except Exception:
        raise ValidationFailedError("Couldn't read this Excel file — it may be damaged. Save it again and retry.")

    best_missing: list[str] | None = None
    for sheet in workbook.worksheets:
        sheet.reset_dimensions()
        rows = sheet.iter_rows(values_only=True)
        for row_number, row in enumerate(rows, start=1):
            if row_number > _HEADER_SEARCH_ROWS:
                break
            columns: dict[str, int] = {}
            for idx, cell in enumerate(row or ()):
                field = _HEADERS.get(" ".join(str(cell).lower().split())) if cell is not None else None
                if field and field not in columns:
                    columns[field] = idx
            if "dc_code" not in columns:
                continue
            missing = [label for field, label in _REQUIRED_FIELDS.items() if field not in columns]
            if missing:
                if best_missing is None or len(missing) < len(best_missing):
                    best_missing = missing
                continue
            return row_number, columns, rows
    if best_missing:
        raise ValidationFailedError(f"This file is missing the column(s): {', '.join(best_missing)}.")
    raise ValidationFailedError(
        "Couldn't find the Keells price columns (DC Code, System Name, Price, Unit, Numeric Price) in this file."
    )


def _check_price(values: dict) -> tuple[float | None, str | None, str | None]:
    """(price, unit, error) for one row. Price text and Numeric Price must agree."""
    unit_raw = values.get("unit")
    unit = _UNITS.get(_norm(unit_raw)) if not _blank(unit_raw) else None
    if _blank(unit_raw):
        return None, None, "Unit is missing."
    if unit is None:
        return None, None, f"Unit '{unit_raw}' isn't one Keells uses — expected KG or Unit."

    numeric_raw = values.get("numeric_price")
    text_raw = values.get("price_text")
    if isinstance(numeric_raw, str) and numeric_raw.strip().upper() in _EXCEL_ERRORS:
        return None, unit, f"Numeric Price is an Excel error ({numeric_raw.strip()})."
    numeric = _number(numeric_raw)
    if not _blank(numeric_raw) and numeric is None:
        return None, unit, f"Numeric Price '{numeric_raw}' isn't a number."

    text_price = None
    if not _blank(text_raw):
        m = _PRICE_TEXT_RE.match(str(text_raw))
        if not m:
            return None, unit, f"Price '{text_raw}' isn't a Keells price like 'Rs 290.00 / KG'."
        text_price = float(m.group(1).replace(",", ""))
        text_unit = _UNITS.get(_norm(m.group(2))) if m.group(2) else None
        if m.group(2) and text_unit != unit:
            return None, unit, f"Price says per {m.group(2)} but Unit says {unit_raw}."

    if numeric is None and text_price is None:
        return None, unit, "Price is missing."
    if numeric is not None and text_price is not None and abs(numeric - text_price) > 0.005:
        return None, unit, f"Price ({text_raw}) and Numeric Price ({numeric_raw}) don't agree."
    price = numeric if numeric is not None else text_price
    if price <= 0:
        return None, unit, "Price must be greater than zero."
    if price > MAX_NUMERIC_10_2:
        return None, unit, f"Price exceeds the maximum allowed value ({MAX_NUMERIC_10_2:,.2f})."
    return round(price, 2), unit, None


def preview_keells_excel(db: Session, delivery_date: date, file_bytes: bytes) -> dict:
    """Validates the whole file and reports row by row. Never saves anything."""
    header_row, columns, rows = _open_rows(file_bytes)
    products = {p.product_code: p for p in db.query(Product).filter(Product.product_code.in_(_REQUIRED_BY_CODE)).all()}

    lines: list[dict] = []
    first_row_for_code: dict[str, int] = {}
    for row_number, row in enumerate(rows, start=header_row + 1):
        if row_number - header_row > MAX_ROWS_SCANNED:
            raise ValidationFailedError(_TOO_BIG)
        row = row or ()
        values = {field: (row[idx] if idx < len(row) else None) for field, idx in columns.items()}
        if all(_blank(v) for v in values.values()):
            continue  # blank trailing rows

        dc_code = _dc_code(values.get("dc_code"))
        system_name = None if _blank(values.get("system_name")) else str(values["system_name"]).strip()
        keells_name = None if _blank(values.get("keells_name")) else str(values["keells_name"]).strip()
        line = {
            "row_number": row_number,
            "dc_code": dc_code or "",
            "system_name": system_name,
            "keells_name": keells_name,
            "product_id": None,
            "product_description": None,
            "unit": None,
            "price": None,
            "error": None,
        }
        lines.append(line)

        price, unit, price_error = _check_price(values)
        line["price"], line["unit"] = price, unit
        product = products.get(dc_code) if dc_code else None
        if product:
            line["product_id"], line["product_description"] = product.id, product.description

        if not dc_code:
            line["error"] = "DC Code is missing."
        elif dc_code in first_row_for_code:
            line["error"] = f"DC Code {dc_code} appears more than once (first on row {first_row_for_code[dc_code]})."
        elif dc_code not in _REQUIRED_BY_CODE:
            line["error"] = f"DC Code {dc_code} isn't on the list of products compared with Keells."
        elif not product:
            line["error"] = f"No product with DC Code {dc_code} in the Product List."
        elif not system_name:
            line["error"] = "System Name is missing."
        elif _norm(system_name) not in {_norm(product.description), _norm(_REQUIRED_BY_CODE[dc_code])}:
            line["error"] = f"System Name '{system_name}' doesn't match DC Code {dc_code} ({product.description})."
        elif product.status != "ACTIVE":
            line["error"] = f"{product.description} has been removed from the Product List."
        elif price_error:
            line["error"] = price_error
        if dc_code and dc_code not in first_row_for_code:
            first_row_for_code[dc_code] = row_number

    valid = [l for l in lines if l["error"] is None]
    in_file = {l["dc_code"] for l in valid}
    not_in_file = [
        {"dc_code": code, "system_name": name}
        for code, name in _REQUIRED_BY_CODE.items()
        if code not in in_file and code in products and products[code].status == "ACTIVE"
    ]
    existing = (
        db.query(MarketReferencePrice)
        .filter(MarketReferencePrice.source == SOURCE, MarketReferencePrice.delivery_date == delivery_date)
        .count()
    )
    return {
        "delivery_date": delivery_date,
        "lines": lines,
        "valid_count": len(valid),
        "error_count": len(lines) - len(valid),
        "not_in_file": not_in_file,
        "existing_count": existing,
    }


def import_keells_excel(db: Session, admin: User, delivery_date: date, file_bytes: bytes, file_name: str | None = None) -> dict:
    """All-or-nothing: replaces delivery_date's KEELLS prices with the file's,
    or raises without changing anything if any row has a problem."""
    preview = preview_keells_excel(db, delivery_date, file_bytes)
    if preview["error_count"]:
        n = preview["error_count"]
        raise ValidationFailedError(
            f"{n} row{'' if n == 1 else 's'} in this file {'has' if n == 1 else 'have'} problems, so nothing was imported. "
            "Fix them and upload the file again."
        )
    if not preview["valid_count"]:
        raise ValidationFailedError("This file has no Keells prices in it, so nothing was imported.")

    prices = {l["product_id"]: l["price"] for l in preview["lines"]}
    try:
        replaced = pricing_service.replace_reference_prices(db, admin, delivery_date, prices, SOURCE)
    except Exception:
        logger.exception("Keells Excel import for %s failed while saving", delivery_date)
        raise
    logger.info("Keells Excel import: %d prices for %s (replaced %d) by user %s", len(prices), delivery_date, replaced, admin.id)
    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="KEELLS_PRICES_IMPORTED",
        entity_type="market_reference_price",
        description=f"Imported {len(prices)} Keells prices for {delivery_date.isoformat()} from Excel (replaced {replaced}).",
        metadata={"delivery_date": delivery_date.isoformat(), "imported": len(prices), "replaced": replaced, "file_name": file_name},
    )
    return {"delivery_date": delivery_date, "imported": len(prices), "replaced": replaced}
