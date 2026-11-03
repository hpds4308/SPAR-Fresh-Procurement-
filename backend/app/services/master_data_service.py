"""
Master Data Sheet: one row per product, combining Admin's own margin
reference fields (target GP%, selling price) with a live view of every
active supplier's most recent Adjusted Price — mirrors the client's
existing spreadsheet workflow (Category / POS code / Description /
Target GP% / Selling / GP% / Keells Price / Cost Price / one column per
supplier's Adjusted CP).

Field ownership:
- selling_price: set manually by Admin here (source MANUAL), or filled
  by Auto-generate where it was blank (source AUTO).
- published_selling_price: what branches see. Only the Master Data Team
  changes it, by publishing the latest sheet Admin sent them (see
  send_to_master_data / publish_selling_prices).
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
import json
from datetime import date, datetime, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.branch import Branch
from app.models.master_data_submission import MasterDataSubmission
from app.models.pricing import SupplierPrice
from app.models.product import Product, ProductCategory
from app.models.selling_price_history import SellingPriceHistory
from app.models.supplier import Supplier
from app.models.user import User
from app.services import price_approval_service, pricing_service
from app.schemas._limits import MAX_NUMERIC_10_2
from app.schemas.master_data import (
    AutoGenerateSummaryOut,
    MasterDataSendOut,
    MasterDataSubmissionOut,
    PublishSummaryOut,
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
                selling_price_source=p.selling_price_source if selling_price is not None else None,
                published_selling_price=(
                    float(p.published_selling_price) if p.published_selling_price is not None else None
                ),
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


def auto_generate_selling_prices(db: Session) -> AutoGenerateSummaryOut:
    """
    Fills in Selling Price for every active product that doesn't have one
    yet, from the GP% formula solved for selling price:

        GP = (selling_price - cost_price) / selling_price
        => selling_price = cost_price / (1 - target_gp_percent)

    then drops the decimals and rounds up to the next 10. Uses each
    product's own target_gp_percent (defaulting to 30% the same way the
    sheet already does).

    A product that already has a selling price — typed by Admin, or
    generated earlier — is never touched, and neither is the price the
    Master Data Team published to branches (a separate column). Products
    with no cost_price yet (no supplier has quoted) stay blank. The rows
    are locked while this runs, so a double click or two Admins at once
    can't both fill the same product; a second run just finds nothing
    left to fill.
    """
    products = db.query(Product).filter(Product.status == "ACTIVE").with_for_update().all()

    latest_prices, _ = _latest_prices(db)
    supplier_ids = [s.id for s in db.query(Supplier).filter(Supplier.status == "ACTIVE").all()]

    generated = preserved = without_price = 0
    for p in products:
        if p.selling_price is not None:
            preserved += 1
            continue
        prices_for_product = [latest_prices[(sid, p.id)] for sid in supplier_ids if (sid, p.id) in latest_prices]
        target_gp = float(p.target_gp_percent) if p.target_gp_percent is not None else 0.30
        if not prices_for_product or target_gp >= 1:
            # No cost price, or can't solve (division by zero or negative) — leave blank rather than guess.
            without_price += 1
            continue
        new_price = round_up_to_10(max(prices_for_product) / (1 - target_gp))
        if new_price > MAX_NUMERIC_10_2:
            without_price += 1
            continue
        p.selling_price = new_price
        p.selling_price_source = "AUTO"
        generated += 1

    db.commit()
    return AutoGenerateSummaryOut(
        total_products=len(products),
        generated=generated,
        preserved=preserved,
        without_price=without_price,
    )


def build_master_data_excel(db: Session) -> bytes:
    """
    Renders the current Master Data Sheet as .xlsx bytes — shared by the
    download endpoint and the "Send to Master Data" email endpoint, so
    the two can never drift into showing different data for the same
    export.
    """
    return sheet_to_excel(get_master_data_sheet(db))


def sheet_to_excel(sheet: MasterDataSheetOut) -> bytes:
    """One sheet as .xlsx — the live one (Admin) or a sent copy (Master Data Team)."""
    import io

    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

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
        product.selling_price_source = "MANUAL" if value is not None else None
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


# --------------------------------------------------------------------------
# Send to Master Data → Master Data Team → Update Selling Prices
# --------------------------------------------------------------------------

# Any constant works — it only has to be the same for every caller, so two
# "Send" clicks (or two "Publish" clicks) run one after the other, never
# interleaved. Released automatically when the transaction ends.
_SEND_LOCK_KEY = 732001
_PUBLISH_LOCK_KEY = 732002


def _sheet_json(sheet: MasterDataSheetOut) -> dict:
    # Through a JSON round-trip so supplier_prices' int keys become the
    # same strings the database hands back — lets "nothing changed" compare equal.
    return json.loads(sheet.model_dump_json())


def _count_with_price(sheet: MasterDataSheetOut) -> int:
    return sum(1 for r in sheet.rows if r.selling_price is not None)


def _latest_submission(db: Session) -> MasterDataSubmission | None:
    return db.query(MasterDataSubmission).order_by(MasterDataSubmission.version.desc()).first()


def send_to_master_data(db: Session, admin: User) -> tuple[MasterDataSendOut, MasterDataSheetOut]:
    """
    Saves the current Master Data Sheet as the next numbered version for
    the Master Data Team. Products aren't copied or created — this is one
    read-only snapshot row. If nothing changed since the last send, no new
    version is made (created=False), so repeated clicks don't pile up
    identical copies. Returns the sheet too, for the optional email.
    """
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SEND_LOCK_KEY})
    sheet = get_master_data_sheet(db)
    if not sheet.rows:
        db.rollback()
        raise ValidationFailedError("There are no active products on the Master Data Sheet to send.")
    for r in sheet.rows:
        if r.selling_price is not None and not (0 < r.selling_price <= MAX_NUMERIC_10_2):
            db.rollback()
            raise ValidationFailedError(f"{r.description} has an invalid selling price — fix it before sending.")

    snapshot = _sheet_json(sheet)
    latest = _latest_submission(db)
    if latest is not None and latest.sheet == snapshot:
        db.commit()  # releases the lock
        return (
            MasterDataSendOut(
                version=latest.version,
                sent_at=latest.sent_at,
                product_count=latest.product_count,
                products_with_price=_count_with_price(sheet),
                created=False,
            ),
            sheet,
        )

    submission = MasterDataSubmission(
        version=(latest.version + 1) if latest else 1,
        sent_by=admin.id,
        product_count=len(sheet.rows),
        sheet=snapshot,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="MASTER_DATA_SENT",
        entity_type="master_data_submission",
        entity_id=submission.id,
        description=f"Sent Master Data Sheet version {submission.version} ({submission.product_count} products).",
    )
    return (
        MasterDataSendOut(
            version=submission.version,
            sent_at=submission.sent_at,
            product_count=submission.product_count,
            products_with_price=_count_with_price(sheet),
            created=True,
        ),
        sheet,
    )


def _display_name(db: Session, user_id: int | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return (user.full_name or user.username) if user else None


def get_latest_submission(db: Session) -> MasterDataSubmissionOut:
    latest = _latest_submission(db)
    if latest is None:
        raise NotFoundError("Admin hasn't sent the Master Data Sheet yet.")
    sheet = MasterDataSheetOut.model_validate(latest.sheet)
    # Everything is as Admin sent it, except "published" — that's what
    # branches see right now, so the team can tell what is still to publish.
    published = dict(
        db.query(Product.id, Product.published_selling_price)
        .filter(Product.id.in_([r.product_id for r in sheet.rows]))
        .all()
    )
    for r in sheet.rows:
        value = published.get(r.product_id)
        r.published_selling_price = float(value) if value is not None else None
    return MasterDataSubmissionOut(
        version=latest.version,
        sent_at=latest.sent_at,
        sent_by=_display_name(db, latest.sent_by) or "—",
        product_count=latest.product_count,
        products_with_price=_count_with_price(sheet),
        published_at=latest.published_at,
        published_by=_display_name(db, latest.published_by),
        publish_summary=latest.publish_summary,
        sheet=sheet,
    )


def publish_selling_prices(db: Session, user: User) -> PublishSummaryOut:
    """
    Publishes the selling prices in the latest sheet Admin sent, so every
    branch sees them. Products are global (one row each, shared by all
    branches), so this updates products.published_selling_price in place —
    nothing is inserted, and order quantities, supplier prices and
    anything branch-specific aren't touched. All-or-nothing: one
    transaction, committed once at the end. Publishing the same version
    again just reports every product as unchanged.

    Skipped: rows with no selling price (missing), and rows whose product
    no longer exists / was removed or whose price is out of range (invalid).
    """
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _PUBLISH_LOCK_KEY})
        latest = _latest_submission(db)
        if latest is None:
            raise ValidationFailedError("Admin hasn't sent the Master Data Sheet yet — there is nothing to publish.")
        sheet = MasterDataSheetOut.model_validate(latest.sheet)

        now = datetime.now(timezone.utc)
        updated = unchanged = 0
        missing: list[str] = []
        invalid: list[str] = []
        products = {
            p.id: p
            for p in db.query(Product)
            .filter(Product.id.in_([r.product_id for r in sheet.rows]))
            .with_for_update()
            .all()
        }
        for row in sheet.rows:
            product = products.get(row.product_id)
            if product is None or product.status != "ACTIVE" or product.product_code != row.product_code:
                invalid.append(row.description)
                continue
            if row.selling_price is None:
                missing.append(row.description)
                continue
            if not (0 < row.selling_price <= MAX_NUMERIC_10_2):
                invalid.append(row.description)
                continue
            if (
                product.published_selling_price is not None
                and float(product.published_selling_price) == row.selling_price
            ):
                unchanged += 1
                continue
            product.published_selling_price = row.selling_price
            product.selling_price_published_at = now
            product.selling_price_published_by = user.id
            db.add(
                SellingPriceHistory(
                    product_id=product.id,
                    price=row.selling_price,
                    published_at=now,
                    published_by=user.id,
                    version=latest.version,
                )
            )
            updated += 1

        if updated == 0 and unchanged == 0:
            raise ValidationFailedError("None of the products in this sheet has a valid selling price to publish.")

        branches = db.query(func.count(Branch.id)).filter(Branch.status == "ACTIVE").scalar() or 0
        summary = PublishSummaryOut(
            version=latest.version,
            published_at=now,
            products_updated=updated,
            products_unchanged=unchanged,
            branches_updated=branches,
            skipped_missing_price=missing,
            skipped_invalid=invalid,
        )
        latest.published_by = user.id
        latest.published_at = now
        latest.publish_summary = json.loads(summary.model_dump_json())
        db.commit()
    except Exception:
        db.rollback()
        raise

    write_audit_log(
        db,
        user_id=user.id,
        role="MASTER_DATA",
        action="SELLING_PRICES_PUBLISHED",
        entity_type="master_data_submission",
        entity_id=latest.id,
        description=(
            f"Published selling prices from version {latest.version}: {updated} updated, {unchanged} unchanged, "
            f"{len(missing)} missing a price, {len(invalid)} invalid."
        ),
    )
    return summary


def latest_submission_excel(db: Session) -> tuple[bytes, str]:
    latest = get_latest_submission(db)
    filename = f"SPAR-Master-Data-Sheet-v{latest.version}-{latest.sent_at.date().isoformat()}.xlsx"
    return sheet_to_excel(latest.sheet), filename
