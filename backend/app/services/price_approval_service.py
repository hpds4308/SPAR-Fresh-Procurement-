"""
Supplier approval (e-signature) of Admin's adjusted prices.

Flow (as agreed with the client):
1. Admin types adjusted prices on Supplier Prices — drafts only Admin sees.
2. Admin clicks "Send for approval" on one supplier's column. Every
   adjusted price for that supplier and delivery date that isn't already
   agreed goes out together as one price sheet (SupplierPriceRevision), so
   the supplier signs once rather than once per item.
3. The supplier reviews the sheet and either approves it — ticking the
   agreement and drawing a signature — or rejects it with a reason.
4. Only an APPROVED adjusted price counts as the agreed price (Master Data
   uses it). If the supplier rejects, or doesn't respond before the
   delivery date arrives, the supplier's own submitted price applies.

An approved sheet is locked: if Admin changes any price on it afterwards,
the whole sheet is voided and its items go back to draft, to be sent and
signed again. Sheets are never deleted — voided/withdrawn/rejected ones
stay as history, with the exact figures in their `items` snapshot.
"""
import base64
import binascii
import hashlib
import json
from datetime import date, datetime, time, timezone, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.security import verify_password
from app.models.price_revision import SupplierPriceRevision
from app.models.pricing import SupplierPrice
from app.models.product import Product
from app.models.supplier import Supplier
from app.models.user import User

# Same business timezone as pricing_service — not imported from there
# because pricing_service imports this module.
BUSINESS_TZ = ZoneInfo("Asia/Colombo")

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
VOIDED = "VOIDED"
WITHDRAWN = "WITHDRAWN"
EXPIRED = "EXPIRED"  # computed only — never stored
DRAFT = "DRAFT"  # row-level only: adjusted but not on any live sheet

# Same limits as the login lockout in auth_service — re-entering a password
# to sign mustn't become a way around it.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

PNG_DATA_URL_PREFIX = "data:image/png;base64,"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_SIGNATURE_BYTES = 250_000


def _now() -> datetime:
    return datetime.now(BUSINESS_TZ)


def expires_at(delivery_date: date) -> datetime:
    """A sheet can be signed up to the start of its delivery date (Colombo time)."""
    return datetime.combine(delivery_date, time(0, 0), tzinfo=BUSINESS_TZ)


def effective_status(rev: SupplierPriceRevision, now: datetime | None = None) -> str:
    if rev.status == PENDING and (now or _now()) >= expires_at(rev.delivery_date):
        return EXPIRED
    return rev.status


def compute_snapshot_hash(supplier_id: int, delivery_date: date, items: list[dict]) -> str:
    payload = json.dumps(
        {"supplier_id": supplier_id, "delivery_date": delivery_date.isoformat(), "items": items},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_items(db: Session, rows: list[SupplierPrice]) -> list[dict]:
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_([r.product_id for r in rows])).all()}
    items = []
    for r in rows:
        product = products.get(r.product_id)
        items.append(
            {
                "supplier_price_id": r.id,
                "product_id": r.product_id,
                "product_code": product.product_code if product else "—",
                "product_description": product.description if product else "—",
                "unit_code": r.unit_code,
                "supplier_price": float(r.price),
                "adjusted_price": float(r.adjusted_price),
            }
        )
    items.sort(key=lambda i: (i["product_description"], i["supplier_price_id"]))
    return items


def _close(db: Session, rev: SupplierPriceRevision, status: str, reason: str) -> None:
    """Void/withdraw a sheet and put every price still on it back to draft. Caller commits."""
    rev.status = status
    rev.closed_reason = reason[:255]
    rev.closed_at = _now()
    for row in db.query(SupplierPrice).filter(SupplierPrice.revision_id == rev.id).all():
        row.revision_id = None
        row.sent_to_supplier_at = None


# ---- Hooks called from pricing_service when the underlying prices change ----


def on_adjusted_price_changed(db: Session, row: SupplierPrice) -> SupplierPriceRevision | None:
    """
    Called (before commit) when Admin changes or clears an adjusted price.
    If the price was on a live sheet (waiting or already approved) the whole
    sheet is voided — the supplier must never be held to figures they
    didn't see. Returns the voided sheet, if any.
    """
    if row.revision_id is None:
        row.sent_to_supplier_at = None
        return None
    rev = db.get(SupplierPriceRevision, row.revision_id)
    if rev and rev.status in (PENDING, APPROVED):
        product = db.get(Product, row.product_id)
        name = product.description if product else f"product #{row.product_id}"
        _close(db, rev, VOIDED, f"Admin changed the price of {name} after the sheet was sent.")
        return rev
    row.revision_id = None
    row.sent_to_supplier_at = None
    return None


def on_supplier_resubmitted(db: Session, supplier_id: int, delivery_date: date) -> int:
    """Supplier resubmitted their prices — any sheet still waiting was based on old quotes. Caller commits."""
    pending = (
        db.query(SupplierPriceRevision)
        .filter(
            SupplierPriceRevision.supplier_id == supplier_id,
            SupplierPriceRevision.delivery_date == delivery_date,
            SupplierPriceRevision.status == PENDING,
        )
        .all()
    )
    for rev in pending:
        _close(db, rev, VOIDED, "The supplier resubmitted their prices after this sheet was sent.")
    return len(pending)


# ---- Row-level status, for the admin and supplier price tables ----


def row_statuses(db: Session, rows: list[SupplierPrice]) -> dict[int, tuple[str | None, SupplierPriceRevision | None]]:
    """(approval status, sheet) per supplier_prices row id. Status is None when there's no adjusted price."""
    rev_ids = {r.revision_id for r in rows if r.revision_id}
    revs = (
        {rev.id: rev for rev in db.query(SupplierPriceRevision).filter(SupplierPriceRevision.id.in_(rev_ids)).all()}
        if rev_ids
        else {}
    )
    now = _now()
    out: dict[int, tuple[str | None, SupplierPriceRevision | None]] = {}
    for r in rows:
        if r.adjusted_price is None:
            out[r.id] = (None, None)
            continue
        rev = revs.get(r.revision_id) if r.revision_id else None
        if rev is None or rev.status in (VOIDED, WITHDRAWN):
            out[r.id] = (DRAFT, None)
        else:
            out[r.id] = (effective_status(rev, now), rev)
    return out


def approved_revision_ids(db: Session, revision_ids: set[int]) -> set[int]:
    if not revision_ids:
        return set()
    return {
        rid
        for (rid,) in db.query(SupplierPriceRevision.id).filter(
            SupplierPriceRevision.id.in_(revision_ids), SupplierPriceRevision.status == APPROVED
        )
    }


# ---- Admin actions ----


def send_for_approval(db: Session, admin: User, supplier_id: int, delivery_date: date) -> SupplierPriceRevision:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise NotFoundError("That supplier was not found.")
    if _now() >= expires_at(delivery_date):
        raise ValidationFailedError(
            f"Delivery on {delivery_date.isoformat()} has already started — prices for it can't be sent for approval."
        )

    rows = (
        db.query(SupplierPrice)
        .filter(
            SupplierPrice.supplier_id == supplier_id,
            SupplierPrice.delivery_date == delivery_date,
            SupplierPrice.adjusted_price.isnot(None),
        )
        .order_by(SupplierPrice.id)
        .all()
    )
    approved = approved_revision_ids(db, {r.revision_id for r in rows if r.revision_id})
    to_send = [r for r in rows if r.revision_id not in approved]
    if not to_send:
        raise ValidationFailedError(
            f"There are no new adjusted prices to send to {supplier.supplier_name} for {delivery_date.isoformat()}."
        )

    # One live sheet per supplier/date: anything still waiting is folded
    # into this new one (its items are in `to_send`) and voided.
    replaced = (
        db.query(SupplierPriceRevision)
        .filter(
            SupplierPriceRevision.supplier_id == supplier_id,
            SupplierPriceRevision.delivery_date == delivery_date,
            SupplierPriceRevision.status == PENDING,
        )
        .all()
    )
    for old in replaced:
        _close(db, old, VOIDED, "Replaced by a newer price sheet.")

    now = _now()
    items = _build_items(db, to_send)
    rev = SupplierPriceRevision(
        supplier_id=supplier_id,
        delivery_date=delivery_date,
        status=PENDING,
        items=items,
        snapshot_hash=compute_snapshot_hash(supplier_id, delivery_date, items),
        sent_by=admin.id,
        sent_at=now,
    )
    db.add(rev)
    db.flush()
    for r in to_send:
        r.revision_id = rev.id
        r.sent_to_supplier_at = now
    db.commit()
    db.refresh(rev)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PRICE_SHEET_SENT",
        entity_type="supplier_price_revision",
        entity_id=rev.id,
        description=(
            f"{len(items)} adjusted price(s) sent to {supplier.supplier_name} for approval "
            f"(delivery {delivery_date.isoformat()})."
            + (f" Replaced {len(replaced)} earlier sheet(s)." if replaced else "")
        ),
    )
    return rev


def withdraw(db: Session, admin: User, revision_id: int) -> SupplierPriceRevision:
    rev = db.get(SupplierPriceRevision, revision_id)
    if not rev:
        raise NotFoundError("That price sheet was not found.")
    if rev.status != PENDING:
        raise ValidationFailedError("Only a price sheet still waiting for the supplier can be withdrawn.")
    _close(db, rev, WITHDRAWN, "Withdrawn by SPAR before the supplier responded.")
    db.commit()
    db.refresh(rev)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PRICE_SHEET_WITHDRAWN",
        entity_type="supplier_price_revision",
        entity_id=rev.id,
        description=f"Price sheet #{rev.id} withdrawn before the supplier responded.",
    )
    return rev


# ---- Supplier actions ----


def _get_own(db: Session, supplier_user: User, revision_id: int) -> SupplierPriceRevision:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can respond to price sheets.")
    rev = db.get(SupplierPriceRevision, revision_id)
    # Another supplier's sheet looks exactly like a missing one.
    if not rev or rev.supplier_id != supplier_user.supplier_id:
        raise NotFoundError("That price sheet was not found.")
    return rev


def _require_open(rev: SupplierPriceRevision, snapshot_hash: str) -> None:
    status = effective_status(rev)
    if status == EXPIRED:
        raise ValidationFailedError(
            f"This price sheet expired when delivery on {rev.delivery_date.isoformat()} started — "
            "your own submitted prices apply."
        )
    if status != PENDING:
        raise ValidationFailedError("This price sheet is no longer waiting for your response. Reload to see the latest.")
    if snapshot_hash != rev.snapshot_hash:
        raise ValidationFailedError("SPAR changed these prices after you opened them. Reload to see the latest.")


def _check_signature_image(data_url: str) -> None:
    if not data_url.startswith(PNG_DATA_URL_PREFIX):
        raise ValidationFailedError("Draw your signature in the box.")
    try:
        raw = base64.b64decode(data_url[len(PNG_DATA_URL_PREFIX):], validate=True)
    except (binascii.Error, ValueError):
        raise ValidationFailedError("Draw your signature in the box.")
    if not raw.startswith(PNG_MAGIC):
        raise ValidationFailedError("Draw your signature in the box.")
    if len(raw) > MAX_SIGNATURE_BYTES:
        raise ValidationFailedError("That signature image is too large. Clear it and sign again.")


def _check_password(db: Session, user: User, password: str) -> None:
    now_utc = datetime.now(timezone.utc)
    if user.locked_until and user.locked_until > now_utc:
        raise PermissionDeniedError("Account temporarily locked due to repeated wrong passwords. Try again later.")
    if not verify_password(password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now_utc + timedelta(minutes=LOCKOUT_MINUTES)
        db.commit()
        raise ValidationFailedError("That password is incorrect.")
    user.failed_login_attempts = 0
    user.locked_until = None


def _check_live_rows_match(db: Session, rev: SupplierPriceRevision) -> None:
    """Belt-and-braces: the stored snapshot is untampered and still matches the live prices on this sheet."""
    if compute_snapshot_hash(rev.supplier_id, rev.delivery_date, rev.items) != rev.snapshot_hash:
        raise ValidationFailedError("This price sheet failed an integrity check. Ask SPAR to send it again.")
    live = {
        r.id: float(r.adjusted_price) if r.adjusted_price is not None else None
        for r in db.query(SupplierPrice).filter(SupplierPrice.revision_id == rev.id).all()
    }
    sent = {i["supplier_price_id"]: i["adjusted_price"] for i in rev.items}
    if live != sent:
        raise ValidationFailedError("SPAR changed these prices after you opened them. Reload to see the latest.")


def approve(
    db: Session,
    supplier_user: User,
    revision_id: int,
    *,
    snapshot_hash: str,
    signer_name: str | None,
    signature_image: str,
    password: str | None,
    ip_address: str | None,
    user_agent: str | None,
) -> SupplierPriceRevision:
    rev = _get_own(db, supplier_user, revision_id)
    _require_open(rev, snapshot_hash)
    _check_signature_image(signature_image)
    if password is not None:
        _check_password(db, supplier_user, password)
    _check_live_rows_match(db, rev)

    rev.status = APPROVED
    rev.responded_by = supplier_user.id
    rev.responded_at = _now()
    rev.signer_name = signer_name
    rev.signature_image = signature_image
    rev.signer_ip = (ip_address or "")[:255] or None
    rev.signer_user_agent = (user_agent or "")[:500] or None
    db.commit()
    db.refresh(rev)

    write_audit_log(
        db,
        user_id=supplier_user.id,
        role="SUPPLIER",
        action="PRICE_SHEET_APPROVED",
        entity_type="supplier_price_revision",
        entity_id=rev.id,
        description=(
            f"Price sheet #{rev.id} ({len(rev.items)} item(s), delivery {rev.delivery_date.isoformat()}) "
            f"e-signed by {signer_name or supplier_user.username}. Snapshot SHA-256 {rev.snapshot_hash}."
        ),
        ip_address=rev.signer_ip,
    )
    return rev


def reject(db: Session, supplier_user: User, revision_id: int, *, snapshot_hash: str, reason: str) -> SupplierPriceRevision:
    rev = _get_own(db, supplier_user, revision_id)
    _require_open(rev, snapshot_hash)

    rev.status = REJECTED
    rev.responded_by = supplier_user.id
    rev.responded_at = _now()
    rev.rejection_reason = reason
    db.commit()
    db.refresh(rev)

    write_audit_log(
        db,
        user_id=supplier_user.id,
        role="SUPPLIER",
        action="PRICE_SHEET_REJECTED",
        entity_type="supplier_price_revision",
        entity_id=rev.id,
        description=f"Price sheet #{rev.id} rejected: {reason}",
    )
    return rev


# ---- Reads ----


def list_revisions(
    db: Session,
    *,
    supplier_id: int | None = None,
    delivery_date: date | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[SupplierPriceRevision]:
    query = db.query(SupplierPriceRevision)
    if supplier_id:
        query = query.filter(SupplierPriceRevision.supplier_id == supplier_id)
    if delivery_date:
        query = query.filter(SupplierPriceRevision.delivery_date == delivery_date)
    if status == EXPIRED:
        query = query.filter(
            SupplierPriceRevision.status == PENDING, SupplierPriceRevision.delivery_date <= _now().date()
        )
    elif status == PENDING:
        query = query.filter(SupplierPriceRevision.status == PENDING, SupplierPriceRevision.delivery_date > _now().date())
    elif status:
        query = query.filter(SupplierPriceRevision.status == status)
    return query.order_by(SupplierPriceRevision.sent_at.desc(), SupplierPriceRevision.id.desc()).limit(limit).all()


def get_revision(db: Session, revision_id: int) -> SupplierPriceRevision:
    rev = db.get(SupplierPriceRevision, revision_id)
    if not rev:
        raise NotFoundError("That price sheet was not found.")
    return rev


def get_own_revision(db: Session, supplier_user: User, revision_id: int) -> SupplierPriceRevision:
    return _get_own(db, supplier_user, revision_id)


def supplier_pending_count(db: Session, supplier_user: User) -> int:
    if not supplier_user.supplier_id:
        return 0
    return (
        db.query(SupplierPriceRevision)
        .filter(
            SupplierPriceRevision.supplier_id == supplier_user.supplier_id,
            SupplierPriceRevision.status == PENDING,
            SupplierPriceRevision.delivery_date > _now().date(),
        )
        .count()
    )


def admin_attention_count(db: Session) -> int:
    """Rejected sheets for upcoming deliveries that Admin hasn't followed up with a newer sheet yet."""
    today = _now().date()
    revs = (
        db.query(SupplierPriceRevision.id, SupplierPriceRevision.supplier_id, SupplierPriceRevision.delivery_date, SupplierPriceRevision.status)
        .filter(SupplierPriceRevision.delivery_date > today)
        .all()
    )
    latest: dict[tuple[int, date], tuple[int, str]] = {}
    for rid, supplier_id, delivery_date, status in revs:
        key = (supplier_id, delivery_date)
        if key not in latest or rid > latest[key][0]:
            latest[key] = (rid, status)
    return sum(1 for _, status in latest.values() if status == REJECTED)


def to_out(db: Session, revs: list[SupplierPriceRevision], detail: bool = False) -> list[dict]:
    supplier_ids = {r.supplier_id for r in revs}
    user_ids = {r.sent_by for r in revs} | {r.responded_by for r in revs if r.responded_by}
    suppliers = {s.id: s.supplier_name for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()} if supplier_ids else {}
    users = {u.id: u.username for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    now = _now()
    out = []
    for r in revs:
        row = {
            "id": r.id,
            "supplier_id": r.supplier_id,
            "supplier_name": suppliers.get(r.supplier_id, "—"),
            "delivery_date": r.delivery_date,
            "status": effective_status(r, now),
            "item_count": len(r.items),
            "sent_at": r.sent_at,
            "sent_by_name": users.get(r.sent_by),
            "responded_at": r.responded_at,
            "responded_by_name": users.get(r.responded_by) if r.responded_by else None,
            "signer_name": r.signer_name,
            "rejection_reason": r.rejection_reason,
            "closed_reason": r.closed_reason,
            "expires_at": expires_at(r.delivery_date),
        }
        if detail:
            row.update(
                items=r.items,
                snapshot_hash=r.snapshot_hash,
                signature_image=r.signature_image,
                signer_ip=r.signer_ip,
                signer_user_agent=r.signer_user_agent,
            )
        out.append(row)
    return out
