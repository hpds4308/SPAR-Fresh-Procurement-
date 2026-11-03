"""
Master Data Team → POS import files, both built from the latest Master
Data Sheet Admin sent:

- Cost Prices: the Cost Price column, split by the supplier whose price
  it is (Cost Price = the highest supplier price in the row, see
  master_data_service); one file per supplier inside a single .zip.
- Selling Prices: every item's Selling Price; one file.

Each file copies SPAR's POS "Transaction" import layout exactly, from the
samples the team uses (assets/pos_cost_price_template.xlsx — 33 columns,
price in DET_CPRICE; assets/pos_selling_price_template.xlsx — 32 columns,
price in DET_SPRICE): DET_LINENO, DET_PROCODE and DET_STOCKCODE (both the
POS code, as text), DET_CS = 1, DET_UNITQTY = 1 and the price; every other
column blank. Items with no POS code can't be imported, so they're left
out of the files and listed separately.
"""
import io
import re
import zipfile
from copy import copy
from pathlib import Path

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.schemas.master_data import (
    CostPriceItemOut,
    CostPricesOut,
    SellingPriceItemOut,
    SellingPricesOut,
    SupplierCostPricesOut,
)
from app.services import master_data_service

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_COST_TEMPLATE = _ASSETS / "pos_cost_price_template.xlsx"
_SELLING_TEMPLATE = _ASSETS / "pos_selling_price_template.xlsx"
_CPRICE_COLUMN = 8  # H: DET_CPRICE in the cost layout
_SPRICE_COLUMN = 9  # I: DET_SPRICE in the selling layout


def get_cost_prices(db: Session) -> CostPricesOut:
    latest = master_data_service.get_latest_submission(db)
    by_supplier: dict[str, list[CostPriceItemOut]] = {}
    no_pos_code: list[str] = []
    for row in latest.sheet.rows:
        if row.cost_price is None or not row.cost_price_supplier_name:
            continue
        if not row.pos_code:
            no_pos_code.append(row.description)
            continue
        by_supplier.setdefault(row.cost_price_supplier_name, []).append(
            CostPriceItemOut(
                product_id=row.product_id,
                product_code=row.product_code,
                pos_code=row.pos_code,
                description=row.description,
                category_name=row.category_name,
                cost_price=row.cost_price,
                price_date=row.cost_price_date,
            )
        )
    return CostPricesOut(
        version=latest.version,
        sent_at=latest.sent_at,
        suppliers=[
            SupplierCostPricesOut(supplier_name=name, items=items)
            for name, items in sorted(by_supplier.items(), key=lambda kv: kv[0].lower())
        ],
        skipped_no_pos_code=no_pos_code,
    )


def get_selling_prices(db: Session) -> SellingPricesOut:
    latest = master_data_service.get_latest_submission(db)
    items: list[SellingPriceItemOut] = []
    no_pos_code: list[str] = []
    no_price = 0
    for row in latest.sheet.rows:
        if row.selling_price is None:
            no_price += 1
            continue
        if not row.pos_code:
            no_pos_code.append(row.description)
            continue
        items.append(
            SellingPriceItemOut(
                product_id=row.product_id,
                product_code=row.product_code,
                pos_code=row.pos_code,
                description=row.description,
                category_name=row.category_name,
                selling_price=row.selling_price,
                published_selling_price=row.published_selling_price,
            )
        )
    return SellingPricesOut(
        version=latest.version,
        sent_at=latest.sent_at,
        items=items,
        skipped_no_pos_code=no_pos_code,
        without_selling_price=no_price,
    )


def _pos_workbook(template: Path, price_column: int, rows: list[tuple[str, float]]) -> bytes:
    """rows: (pos_code, price). Fills the template's Transaction sheet like the team's sample."""
    wb = load_workbook(template)
    ws = wb["Transaction"]
    # Row 2 of the template still carries the sample's cell formats (text
    # codes, price format) — reuse them for every row written.
    styles = {col: copy(ws.cell(row=2, column=col)._style) for col in range(1, price_column + 1)}
    for i, (pos_code, price) in enumerate(rows, start=1):
        r = i + 1
        values = {1: i, 2: pos_code, 4: pos_code, 6: 1, 7: 1, price_column: price}
        for col, value in values.items():
            cell = ws.cell(row=r, column=col, value=value)
            cell._style = copy(styles[col])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _safe_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", name).strip()
    return re.sub(r"\s+", " ", cleaned) or "Supplier"


def cost_prices_zip(db: Session) -> tuple[bytes, str]:
    data = get_cost_prices(db)
    buf = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for supplier in data.suppliers:
            base = f"{_safe_filename(supplier.supplier_name)} Cost Prices"
            name, n = base, 2
            while name.lower() in used:
                name, n = f"{base} ({n})", n + 1
            used.add(name.lower())
            zf.writestr(
                f"{name}.xlsx",
                _pos_workbook(_COST_TEMPLATE, _CPRICE_COLUMN, [(i.pos_code, i.cost_price) for i in supplier.items]),
            )
    filename = f"SPAR-Cost-Prices-v{data.version}-{data.sent_at.date().isoformat()}.zip"
    return buf.getvalue(), filename


def selling_prices_excel(db: Session) -> tuple[bytes, str]:
    data = get_selling_prices(db)
    content = _pos_workbook(_SELLING_TEMPLATE, _SPRICE_COLUMN, [(i.pos_code, i.selling_price) for i in data.items])
    return content, f"SPAR-Selling-Prices-v{data.version}-{data.sent_at.date().isoformat()}.xlsx"
