"""
Master Data Sheet: one row per product, combining Admin's own margin
reference fields (target GP%, selling price) with a live view of every
active supplier's most recent Adjusted Price — mirrors the client's
existing spreadsheet workflow (Category / POS code / Description /
Target GP% / Selling / GP% / Keells Price / Cost Price / one column per
supplier's Adjusted CP).

Field ownership:
- selling_price: set manually by Admin here.
- target_gp_percent: set manually by Admin here; defaults to 30% (0.30)
  for every product until overridden.
- pos_code: NOT editable — fixed, sourced from the original uploaded
  product data (database/seed/products.csv). If it ever needs
  re-syncing (e.g. after test data drifted), run
  scripts/restore_pos_codes.py rather than editing it here.
- cost_price: NOT editable — the highest of the per-supplier prices
  shown in the same row (SPAR's sent price where there is one, else the
  supplier's submitted price — see _latest_prices). Computed live, never
  stored.
- keells_price: NOT editable — the most recent Keells retail price for
  the product, any date. Read-only mirror of Keells Prices.
- Supplier Adjusted CP columns: read-only mirror of Supplier Prices,
  showing Admin's Adjusted Price where the supplier has approved it. Edit there, not
  here — there is exactly one place a supplier's price can be changed,
  never two disagreeing UIs.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models.pricing import SupplierPrice
from app.models.product import Product, ProductCategory
from app.models.supplier import Supplier
from app.services import price_approval_service, pricing_service
from app.schemas.master_data import (
    MasterDataRowOut,
    MasterDataSheetOut,
    MasterDataSupplierColumn,
    MasterDataField,
    round_up_to_10,
)


def _latest_prices(
    db: Session,
) -> tuple[dict[tuple[int, int], float], dict[tuple[int, int], date]]:
    """
    For every (supplier_id, product_id) pair, that supplier's most recent
    quote, regardless of delivery date:

    - `prices`: SPAR's price once Admin has sent it to the supplier (the
      latest one sent, i.e. SPAR's final price after a second round),
      whether the supplier approved it, rejected it or never answered;
      otherwise the submitted price. Shown in the per-supplier columns,
      and Cost Price is the highest of these. A draft adjustment that was
      never sent doesn't count. Only this sheet works this way — Supplier
      Orders, POs and the supplier's Final Prices use the agreed price
      (see price_approval_service.row_statuses).
    - `dates`: the delivery date that quote was submitted for, so the
      sheet can show which supplier's price is the Cost Price and when.
    """
    rows = (
        db.query(SupplierPrice)
        .order_by(SupplierPrice.supplier_id, SupplierPrice.product_id, SupplierPrice.delivery_date.desc(), SupplierPrice.id.desc())
        .all()
    )
    latest: dict[tuple[int, int], SupplierPrice] = {}
    for r in rows:
        latest.setdefault((r.supplier_id, r.product_id), r)
    spar_prices = price_approval_service.sent_prices(db, list(latest.values()))
    prices = {key: spar_prices.get(r.id, float(r.price)) for key, r in latest.items()}
    dates = {key: r.delivery_date for key, r in latest.items()}
    return prices, dates


def get_master_data_sheet(db: Session) -> MasterDataSheetOut:
    suppliers = db.query(Supplier).filter(Supplier.status == "ACTIVE").order_by(Supplier.supplier_name).all()
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    # Category IDs match the requested display grouping (1=Fruit, 2=Vege
    # Low, 3=Vege Pola, 4=Vege Up); alphabetical within each category.
    products = (
        db.query(Product)
        .filter(Product.status == "ACTIVE")
        .order_by(Product.category_id, Product.description)
        .all()
    )
    latest_prices, latest_dates = _latest_prices(db)
    keells = {r.product_id: r for r in pricing_service.get_last_reference_prices(db, "KEELLS")}

    rows = []
    for p in products:
        supplier_prices = {s.id: latest_prices.get((s.id, p.id)) for s in suppliers}
        # Cost Price = the highest of the supplier prices shown in this
        # row's supplier columns. Also track which supplier + delivery date
        # it came from, so Admin can see who it was and when.
        cost_price = None
        cost_price_supplier_name = None
        cost_price_date = None
        quoted = [s for s in suppliers if supplier_prices[s.id] is not None]
        if quoted:
            winner = max(quoted, key=lambda s: supplier_prices[s.id])
            cost_price = supplier_prices[winner.id]
            cost_price_supplier_name = winner.supplier_name
            cost_price_date = latest_dates[(winner.id, p.id)]

        selling_price = float(p.selling_price) if p.selling_price is not None else None
        computed_gp = None
        if selling_price is not None and cost_price is not None and selling_price > 0:
            computed_gp = round((selling_price - cost_price) / selling_price, 4)

        # Target GP% defaults to 30% for every product until Admin overrides it.
        target_gp = float(p.target_gp_percent) if p.target_gp_percent is not None else 0.30

        keells_row = keells.get(p.id)

        rows.append(
            MasterDataRowOut(
                product_id=p.id,
                product_code=p.product_code,
                pos_code=p.pos_code,
                description=p.description,
                category_name=categories.get(p.category_id, "—"),
                target_gp_percent=target_gp,
                selling_price=selling_price,
                computed_gp_percent=computed_gp,
                keells_price=float(keells_row.price) if keells_row else None,
                keells_price_date=keells_row.delivery_date if keells_row else None,
                cost_price=cost_price,
                cost_price_supplier_name=cost_price_supplier_name,
                cost_price_date=cost_price_date,
                supplier_prices=supplier_prices,
            )
        )

    return MasterDataSheetOut(
        suppliers=[MasterDataSupplierColumn(supplier_id=s.id, supplier_name=s.supplier_name) for s in suppliers],
        rows=rows,
    )


def auto_generate_selling_prices(db: Session) -> int:
    """
    Recalculates Selling Price for every active product, from the GP%
    formula solved for selling price:

        GP = (selling_price - cost_price) / selling_price
        => selling_price = cost_price / (1 - target_gp_percent)

    then drops the decimals and rounds up to the next 10. Uses each
    product's own target_gp_percent (defaulting to 30% the same way the
    sheet already does). Overwrites any existing selling price, including
    manually typed ones. Products with no cost_price yet (no supplier has
    submitted a price) are skipped and keep whatever they had. Returns how
    many rows actually changed.
    """
    products = db.query(Product).filter(Product.status == "ACTIVE").all()
    if not products:
        return 0

    latest_prices, _ = _latest_prices(db)
    supplier_ids = [s.id for s in db.query(Supplier).filter(Supplier.status == "ACTIVE").all()]

    updated = 0
    for p in products:
        prices_for_product = [latest_prices[(sid, p.id)] for sid in supplier_ids if (sid, p.id) in latest_prices]
        if not prices_for_product:
            continue
        cost_price = max(prices_for_product)

        target_gp = float(p.target_gp_percent) if p.target_gp_percent is not None else 0.30
        if target_gp >= 1:
            continue  # can't solve (division by zero or negative) — leave blank rather than guess

        new_price = round_up_to_10(cost_price / (1 - target_gp))
        if p.selling_price is not None and float(p.selling_price) == new_price:
            continue
        p.selling_price = new_price
        updated += 1

    if updated:
        db.commit()
    return updated


def build_master_data_excel(db: Session) -> bytes:
    """
    Renders the current Master Data Sheet as .xlsx bytes — shared by the
    download endpoint and the "Send to Master Data" email endpoint, so
    the two can never drift into showing different data for the same
    export.
    """
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    sheet = get_master_data_sheet(db)

    wb = Workbook()
    ws = wb.active
    ws.title = "Master Data Sheet"

    header = [
        "Category",
        "Supplier Product Code",
        "My POS Code",
        "Description",
        "Target GP%",
        "Selling Price",
        "GP% After Selling Price Change",
        "Keells Price",
        "Cost Price",
    ] + [s.supplier_name for s in sheet.suppliers]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        cell.alignment = Alignment(horizontal="center", wrap_text=True)

    below_target_fill = PatternFill(start_color="FCE4E4", end_color="FCE4E4", fill_type="solid")

    for row in sheet.rows:
        values = [
            row.category_name,
            row.product_code,
            row.pos_code,
            row.description,
            row.target_gp_percent,
            row.selling_price,
            row.computed_gp_percent,
            row.keells_price,
            row.cost_price,
        ] + [row.supplier_prices.get(s.supplier_id) for s in sheet.suppliers]
        ws.append(values)
        excel_row = ws.max_row
        if row.computed_gp_percent is not None and row.computed_gp_percent < row.target_gp_percent:
            ws.cell(row=excel_row, column=7).fill = below_target_fill

    for r in range(2, ws.max_row + 1):
        for col in (5, 7):
            cell = ws.cell(row=r, column=col)
            if cell.value is not None:
                cell.number_format = "0.0%"
        for col in (6, 8, 9) + tuple(range(10, 10 + len(sheet.suppliers))):
            cell = ws.cell(row=r, column=col)
            if cell.value is not None:
                cell.number_format = '"Rs. "#,##0.00'

    widths = [12, 16, 12, 32, 11, 12, 14, 12, 11] + [16] * len(sheet.suppliers)
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "E2"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def update_master_data_field(
    db: Session, product_id: int, field: MasterDataField, value
) -> MasterDataRowOut:
    product = db.get(Product, product_id)
    if not product:
        raise NotFoundError("Product not found.")

    if field == "target_gp_percent":
        product.target_gp_percent = value
    elif field == "selling_price":
        product.selling_price = value
    # cost_price is intentionally not settable here — it's always derived
    # as the highest current supplier price, computed in get_master_data_sheet.

    db.commit()
    db.refresh(product)

    sheet = get_master_data_sheet(db)
    for row in sheet.rows:
        if row.product_id == product_id:
            return row
    # Product exists but might be inactive/filtered out of the sheet — return a
    # minimal row built directly rather than pretending nothing happened.
    category = db.get(ProductCategory, product.category_id)
    return MasterDataRowOut(
        product_id=product.id,
        product_code=product.product_code,
        pos_code=product.pos_code,
        description=product.description,
        category_name=category.name if category else "—",
        target_gp_percent=float(product.target_gp_percent) if product.target_gp_percent is not None else 0.30,
        selling_price=float(product.selling_price) if product.selling_price is not None else None,
        computed_gp_percent=None,
        cost_price=None,
        supplier_prices={},
    )
