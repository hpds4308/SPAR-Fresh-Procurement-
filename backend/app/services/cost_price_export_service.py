"""
Master Data Team → Cost Prices: the Cost Price column of the latest
Master Data Sheet Admin sent, split by the supplier whose price it is
(Cost Price = the highest supplier price in the row, see
master_data_service), and downloadable as one POS import file per
supplier inside a single .zip.

Each file copies SPAR's POS "Transaction" import layout exactly
(assets/pos_cost_price_template.xlsx, from the sample the team uses):
DET_LINENO, DET_PROCODE and DET_STOCKCODE (both the POS code, as text),
DET_CS = 1, DET_UNITQTY = 1, DET_CPRICE = the cost price; every other
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

from app.schemas.master_data import CostPriceItemOut, CostPricesOut, SupplierCostPricesOut
from app.services import master_data_service

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "pos_cost_price_template.xlsx"


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


def _supplier_workbook(items: list[CostPriceItemOut]) -> bytes:
    wb = load_workbook(_TEMPLATE_PATH)
    ws = wb["Transaction"]
    # Row 2 of the template still carries the sample's cell formats (text
    # codes, accounting price) — reuse them for every row written.
    styles = {col: copy(ws.cell(row=2, column=col)._style) for col in range(1, 9)}
    for i, item in enumerate(items, start=1):
        r = i + 1
        values = {1: i, 2: item.pos_code, 4: item.pos_code, 6: 1, 7: 1, 8: item.cost_price}
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
            zf.writestr(f"{name}.xlsx", _supplier_workbook(supplier.items))
    filename = f"SPAR-Cost-Prices-v{data.version}-{data.sent_at.date().isoformat()}.zip"
    return buf.getvalue(), filename
