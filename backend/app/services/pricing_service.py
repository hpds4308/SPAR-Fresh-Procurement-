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
from app.schemas.pricing import PriceSubmitRequest, PriceWindowOut
from app.services import settings_service

BUSINESS_TZ = ZoneInfo("Asia/Colombo")


def _parse_cutoff(cutoff_str: str) -> time:
    hh, mm = cutoff_str.split(":")
    return time(hour=int(hh), minute=int(mm))


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
    is_open = now.time() < _parse_cutoff(cutoff_str)
    delivery_date = now.date() + timedelta(days=2)
    return PriceWindowOut(
        is_open=is_open,
        delivery_date=delivery_date,
        cutoff_time=cutoff_str,
        server_time=now.isoformat(),
    )


def submit_prices(db: Session, supplier_user: User, payload: PriceSubmitRequest) -> list[SupplierPrice]:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can submit prices.")

    window = get_price_window(db)
    if not window.is_open:
        raise ValidationFailedError(
            f"Price submission for {window.delivery_date.isoformat()} is closed. "
            f"Daily cutoff is {window.cutoff_time}."
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

    write_audit_log(
        db,
        user_id=supplier_user.id,
        role="SUPPLIER",
        action="PRICES_SUBMITTED",
        entity_type="supplier_price",
        entity_id=supplier_user.supplier_id,
        description=f"{len(payload.prices)} price(s) submitted for delivery {window.delivery_date.isoformat()}.",
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
    without going product-by-product. Defaults to the current price
    window's delivery date (2 days out) when none is given.
    """
    if delivery_date is None:
        delivery_date = get_price_window(db).delivery_date

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
