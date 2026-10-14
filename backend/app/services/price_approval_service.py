"""
Supplier approval (e-signature) of Admin's adjusted prices.

Flow (as agreed with the client):
1. Admin types adjusted prices on Supplier Prices — drafts only Admin sees.
2. Admin clicks "Send for approval" on one supplier's column. Every
   adjusted price for that supplier and delivery date that isn't already
   agreed goes out together as one price sheet (SupplierPriceRevision), so
   the supplier signs once rather than once per item.
3. The supplier answers each item on the sheet: approve it, or reject it
   and optionally give their own final price for it. If they approve at
   least one item they tick the agreement and draw a signature. The sheet
   becomes APPROVED (every item approved), REJECTED (every item rejected)
   or PARTIAL (some of each).
4. An approved item's adjusted price is the agreed price (Master Data uses
   it). A rejected item uses the supplier's final price if they gave one,
   else their own submitted price — as does every item when the supplier
   doesn't respond by the approval cutoff: 2:00 PM (Admin > Settings) on
   the price submission day, two days before delivery. Admin can adjust a
   rejected item again and send it on a new sheet.
5. That re-sent price is SPAR's final offer: the supplier can only approve
   or reject it, with no new price of their own. Rejecting it keeps the
   final price they gave last time (else their submitted price).

Approved items are locked: if Admin changes an approved price afterwards,
the whole sheet is voided and its items go back to draft, to be sent and
signed again. Changing a rejected item only takes that item off the sheet. Sheets are never deleted — voided/withdrawn/rejected ones
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
from app.services import settings_service

# Same business timezone as pricing_service — not imported from there
# because pricing_service imports this module.
BUSINESS_TZ = ZoneInfo("Asia/Colombo")

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
PARTIAL = "PARTIAL"  # some items approved, the rest rejected
VOIDED = "VOIDED"
WITHDRAWN = "WITHDRAWN"
EXPIRED = "EXPIRED"  # computed only — never stored
DRAFT = "DRAFT"  # row-level only: adjusted but not on any live sheet
# Sheets the supplier has answered — each item on them is APPROVED or REJECTED.
RESPONDED = (APPROVED, REJECTED, PARTIAL)

# Same limits as the login lockout in auth_service — re-entering a password
# to sign mustn't become a way around it.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15

PNG_DATA_URL_PREFIX = "data:image/png;base64,"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_SIGNATURE_BYTES = 250_000


def _now() -> datetime:
    return datetime.now(BUSINESS_TZ)


# Prices are submitted two days before delivery (pricing_service.get_price_window).
SUBMISSION_DAYS_BEFORE_DELIVERY = 2


def approval_cutoff(db: Session) -> time:
    """Admin > Settings "Supplier approval cutoff", e.g. 14:00."""
    hh, mm = settings_service.get_setting(db, settings_service.SUPPLIER_APPROVAL_DEADLINE).split(":")
    return time(int(hh), int(mm))


def expires_at(delivery_date: date, cutoff: time) -> datetime:
    """
    A sheet can be answered until the approval cutoff on the price
    submission day (two days before delivery), Colombo time. After that
    the supplier can't change anything and their own prices apply.
    """
    submission_day = delivery_date - timedelta(days=SUBMISSION_DAYS_BEFORE_DELIVERY)
    return datetime.combine(submission_day, cutoff, tzinfo=BUSINESS_TZ)


def _last_closed_delivery_date(cutoff: time, now: datetime | None = None) -> date:
    """The latest delivery date whose approval cutoff has already passed."""
    now = now or _now()
    return now.date() + timedelta(days=SUBMISSION_DAYS_BEFORE_DELIVERY - (0 if now.time() >= cutoff else 1))


def format_cutoff(cutoff: time) -> str:
    """time(14, 0) -> "2:00 PM"."""
    return f"{(cutoff.hour % 12) or 12}:{cutoff.minute:02d} {'AM' if cutoff.hour < 12 else 'PM'}"


def effective_status(rev: SupplierPriceRevision, cutoff: time, now: datetime | None = None) -> str:
    if rev.status == PENDING and (now or _now()) >= expires_at(rev.delivery_date, cutoff):
        return EXPIRED
    return rev.status


def compute_snapshot_hash(supplier_id: int, delivery_date: date, items: list[dict]) -> str:
    payload = json.dumps(
        {"supplier_id": supplier_id, "delivery_date": delivery_date.isoformat(), "items": items},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _previous_rejections(db: Session, rows: list[SupplierPrice]) -> dict[int, float | None]:
    """
    {supplier_prices row id: the final price the supplier gave (or None)}
    for rows whose adjusted price the supplier has already rejected on an
    earlier sheet — the latest rejection wins. A rejection only counts while
    the supplier's quote is still the one they rejected against.
    """
    if not rows:
        return {}
    keys = {(r.supplier_id, r.delivery_date) for r in rows}
    by_id = {r.id: r for r in rows}
    revs = (
        db.query(SupplierPriceRevision)
        .filter(
            SupplierPriceRevision.supplier_id.in_({k[0] for k in keys}),
            SupplierPriceRevision.delivery_date.in_({k[1] for k in keys}),
            SupplierPriceRevision.status.in_((REJECTED, PARTIAL)),
        )
        .order_by(SupplierPriceRevision.id)
        .all()
    )
    out: dict[int, float | None] = {}
    for rev in revs:
        quoted = {i["supplier_price_id"]: i["supplier_price"] for i in rev.items}
        for spid, response in item_responses(rev).items():
            row = by_id.get(spid)
            if response["decision"] == REJECTED and row and quoted.get(spid) == float(row.price):
                out[spid] = response.get("counter_price")
    return out


def _build_items(db: Session, rows: list[SupplierPrice]) -> list[dict]:
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_([r.product_id for r in rows])).all()}
    rejected_before = _previous_rejections(db, rows)
    items = []
    for r in rows:
        product = products.get(r.product_id)
        final_offer = r.id in rejected_before
        items.append(
            {
                "supplier_price_id": r.id,
                "product_id": r.product_id,
                "product_code": product.product_code if product else "—",
                "product_description": product.description if product else "—",
                "unit_code": r.unit_code,
                "supplier_price": float(r.price),
                "adjusted_price": float(r.adjusted_price),
                # Already rejected once: this is SPAR's final price — the
                # supplier can only approve or reject it. Rejecting keeps
                # `previous_price`, the final price they gave last time.
                "final_offer": final_offer,
                "previous_price": rejected_before.get(r.id) if final_offer else None,
            }
        )
    items.sort(key=lambda i: (i["product_description"], i["supplier_price_id"]))
    return items


def item_responses(rev: SupplierPriceRevision) -> dict[int, dict]:
    """
    {supplier_price_id: {"decision", "counter_price"}} for an answered
    sheet. Sheets answered before item-wise responses existed have no
    `item_responses`: every item on them shares the sheet's status.
    """
    if rev.status not in RESPONDED:
        return {}
    if rev.item_responses:
        return {r["supplier_price_id"]: r for r in rev.item_responses}
    return {i["supplier_price_id"]: {"decision": rev.status, "counter_price": None} for i in rev.items}


def _row_decision(rev: SupplierPriceRevision, row_id: int) -> dict | None:
    return item_responses(rev).get(row_id)


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
    # A rejected item on a part-approved sheet just comes off it — the
    # items the supplier did approve stay agreed.
    decision = _row_decision(rev, row.id) if rev and rev.status == PARTIAL else None
    if rev and (rev.status in (PENDING, APPROVED) or (decision and decision["decision"] == APPROVED)):
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


def row_statuses(
    db: Session, rows: list[SupplierPrice]
) -> dict[int, tuple[str | None, SupplierPriceRevision | None, float | None]]:
    """
    (approval status, sheet, supplier's final price) per supplier_prices
    row id. Status is None when there's no adjusted price; on an answered
    sheet it's this item's own APPROVED/REJECTED. The final price is only
    set for a rejected item the supplier gave their own price for.
    """
    rev_ids = {r.revision_id for r in rows if r.revision_id}
    revs = (
        {rev.id: rev for rev in db.query(SupplierPriceRevision).filter(SupplierPriceRevision.id.in_(rev_ids)).all()}
        if rev_ids
        else {}
    )
    now = _now()
    cutoff = approval_cutoff(db)
    out: dict[int, tuple[str | None, SupplierPriceRevision | None, float | None]] = {}
    for r in rows:
        if r.adjusted_price is None:
            out[r.id] = (None, None, None)
            continue
        rev = revs.get(r.revision_id) if r.revision_id else None
        if rev is None or rev.status in (VOIDED, WITHDRAWN):
            out[r.id] = (DRAFT, None, None)
            continue
        decision = _row_decision(rev, r.id)
        if decision:
            out[r.id] = (decision["decision"], rev, decision.get("counter_price"))
        else:
            out[r.id] = (effective_status(rev, cutoff, now), rev, None)
    return out


def agreed_prices(db: Session, rows: list[SupplierPrice]) -> dict[int, float]:
    """
    The price agreed through a price sheet, per supplier_prices row id:
    Admin's adjusted price for an approved item, or the supplier's own
    final price for a rejected item they gave one for. Rows with neither
    aren't in the result — their submitted price applies.
    """
    rev_ids = {r.revision_id for r in rows if r.revision_id and r.adjusted_price is not None}
    if not rev_ids:
        return {}
    revs = {
        rev.id: rev
        for rev in db.query(SupplierPriceRevision).filter(
            SupplierPriceRevision.id.in_(rev_ids), SupplierPriceRevision.status.in_(RESPONDED)
        )
    }
    responses = {rid: item_responses(rev) for rid, rev in revs.items()}
    out: dict[int, float] = {}
    for r in rows:
        if r.adjusted_price is None or r.revision_id not in responses:
            continue
        decision = responses[r.revision_id].get(r.id)
        if not decision:
            continue
        if decision["decision"] == APPROVED:
            out[r.id] = float(r.adjusted_price)
        elif decision.get("counter_price") is not None:
            out[r.id] = float(decision["counter_price"])
    return out


def _approved_row_ids(db: Session, rows: list[SupplierPrice]) -> set[int]:
    return {row_id for row_id, (status, _, _) in row_statuses(db, rows).items() if status == APPROVED}


# ---- Admin actions ----


def send_for_approval(db: Session, admin: User, supplier_id: int, delivery_date: date) -> SupplierPriceRevision:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise NotFoundError("That supplier was not found.")
    cutoff = approval_cutoff(db)
    if _now() >= expires_at(delivery_date, cutoff):
        raise ValidationFailedError(
            f"The {format_cutoff(cutoff)} approval cutoff for delivery on {delivery_date.isoformat()} has passed — "
            "prices for it can't be sent for approval any more."
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
    approved = _approved_row_ids(db, rows)
    to_send = [r for r in rows if r.id not in approved]
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


def _require_open(db: Session, rev: SupplierPriceRevision, snapshot_hash: str) -> None:
    cutoff = approval_cutoff(db)
    status = effective_status(rev, cutoff)
    if status == EXPIRED:
        closed = expires_at(rev.delivery_date, cutoff)
        raise ValidationFailedError(
            f"This price sheet closed at {format_cutoff(cutoff)} on {closed.strftime('%A %d %B')} — "
            "it can't be approved or rejected any more, and your own submitted prices apply."
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


MAX_PRICE = 10_000_000  # same ceiling as supplier_prices.price (Numeric(10, 2))


def _check_decisions(rev: SupplierPriceRevision, decisions: list[dict]) -> list[dict]:
    """
    Validates one answer per item on the sheet and returns them in the
    stored shape, in the sheet's item order.
    """
    items = {i["supplier_price_id"]: i for i in rev.items}
    given: dict[int, dict] = {}
    for d in decisions:
        spid = d["supplier_price_id"]
        if spid not in items:
            raise ValidationFailedError("One of those items isn't on this price sheet. Reload to see the latest.")
        if spid in given:
            raise ValidationFailedError("Each item can only be answered once.")
        given[spid] = d
    missing = [i["product_description"] for i in rev.items if i["supplier_price_id"] not in given]
    if missing:
        raise ValidationFailedError(f"Approve or reject every item. Still to answer: {', '.join(missing)}.")

    out = []
    for item in rev.items:
        d = given[item["supplier_price_id"]]
        decision = d["decision"]
        if decision not in (APPROVED, REJECTED):
            raise ValidationFailedError("Each item must be approved or rejected.")
        counter = d.get("counter_price")
        if item.get("final_offer"):
            if counter is not None:
                raise ValidationFailedError(
                    f"{item['product_description']} is SPAR's final price — approve or reject it, without a new price."
                )
            # Rejecting a final offer keeps the price they gave last time.
            counter = item.get("previous_price") if decision == REJECTED else None
        elif decision == APPROVED or counter is None:
            counter = None
        else:
            counter = round(float(counter), 2)
            if counter <= 0 or counter >= MAX_PRICE:
                raise ValidationFailedError(f"Enter a valid new price for {item['product_description']}.")
            if counter == round(float(item["adjusted_price"]), 2):
                raise ValidationFailedError(
                    f"Your new price for {item['product_description']} is the same as SPAR's. Approve it instead."
                )
        out.append({"supplier_price_id": item["supplier_price_id"], "decision": decision, "counter_price": counter})
    return out


def respond(
    db: Session,
    supplier_user: User,
    revision_id: int,
    *,
    snapshot_hash: str,
    decisions: list[dict],
    note: str | None,
    signature_image: str | None,
    agreed: bool,
    signer_name: str | None = None,
    password: str | None = None,
    ip_address: str | None,
    user_agent: str | None,
) -> SupplierPriceRevision:
    """
    The supplier's answer to a sheet, item by item: each item APPROVED or
    REJECTED (optionally with their own final price). Approving anything
    needs the agreement tick and a drawn signature; rejecting everything
    needs neither.
    """
    rev = _get_own(db, supplier_user, revision_id)
    _require_open(db, rev, snapshot_hash)
    responses = _check_decisions(rev, decisions)
    approved = [r for r in responses if r["decision"] == APPROVED]
    rejected = [r for r in responses if r["decision"] == REJECTED]

    if approved:
        if not agreed:
            raise ValidationFailedError("Tick the box to confirm you agree to the prices you approved.")
        if not signature_image:
            raise ValidationFailedError("Draw your signature in the box.")
        _check_signature_image(signature_image)
        if password is not None:
            _check_password(db, supplier_user, password)
    _check_live_rows_match(db, rev)

    rev.status = APPROVED if not rejected else REJECTED if not approved else PARTIAL
    rev.item_responses = responses
    rev.responded_by = supplier_user.id
    rev.responded_at = _now()
    rev.rejection_reason = (note or None) if rejected else None
    rev.signer_ip = (ip_address or "")[:255] or None
    rev.signer_user_agent = (user_agent or "")[:500] or None
    if approved:
        rev.signer_name = signer_name
        rev.signature_image = signature_image
    db.commit()
    db.refresh(rev)

    names = {i["supplier_price_id"]: i["product_description"] for i in rev.items}

    def describe(r: dict) -> str:
        if r["counter_price"] is None:
            return names[r["supplier_price_id"]]
        return f"{names[r['supplier_price_id']]} (supplier's price {r['counter_price']:.2f})"

    parts = [f"Price sheet #{rev.id} (delivery {rev.delivery_date.isoformat()})"]
    if approved:
        parts.append(f"{len(approved)} item(s) approved and e-signed by {signer_name or supplier_user.username}")
    if rejected:
        parts.append(f"{len(rejected)} item(s) rejected: {', '.join(describe(r) for r in rejected)}")
    if note and rejected:
        parts.append(f"Note: {note}")
    action = {APPROVED: "PRICE_SHEET_APPROVED", REJECTED: "PRICE_SHEET_REJECTED", PARTIAL: "PRICE_SHEET_PARTIAL"}[rev.status]
    write_audit_log(
        db,
        user_id=supplier_user.id,
        role="SUPPLIER",
        action=action,
        entity_type="supplier_price_revision",
        entity_id=rev.id,
        description=". ".join(parts) + f". Snapshot SHA-256 {rev.snapshot_hash}.",
        ip_address=rev.signer_ip,
    )
    return rev


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
    """Approve every item on the sheet at once."""
    rev = _get_own(db, supplier_user, revision_id)
    return respond(
        db,
        supplier_user,
        revision_id,
        snapshot_hash=snapshot_hash,
        decisions=[{"supplier_price_id": i["supplier_price_id"], "decision": APPROVED} for i in rev.items],
        note=None,
        signature_image=signature_image,
        agreed=True,
        signer_name=signer_name,
        password=password,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def reject(db: Session, supplier_user: User, revision_id: int, *, snapshot_hash: str, reason: str) -> SupplierPriceRevision:
    """Reject every item on the sheet at once, with a reason."""
    rev = _get_own(db, supplier_user, revision_id)
    return respond(
        db,
        supplier_user,
        revision_id,
        snapshot_hash=snapshot_hash,
        decisions=[{"supplier_price_id": i["supplier_price_id"], "decision": REJECTED} for i in rev.items],
        note=reason,
        signature_image=None,
        agreed=False,
        ip_address=None,
        user_agent=None,
    )


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
    last_closed = _last_closed_delivery_date(approval_cutoff(db))
    if status == EXPIRED:
        query = query.filter(SupplierPriceRevision.status == PENDING, SupplierPriceRevision.delivery_date <= last_closed)
    elif status == PENDING:
        query = query.filter(SupplierPriceRevision.status == PENDING, SupplierPriceRevision.delivery_date > last_closed)
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
            SupplierPriceRevision.delivery_date > _last_closed_delivery_date(approval_cutoff(db)),
        )
        .count()
    )


def admin_attention_count(db: Session) -> int:
    """Sheets with rejected items, still open to a new sheet, that Admin hasn't followed up yet."""
    today = _last_closed_delivery_date(approval_cutoff(db))
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
    return sum(1 for _, status in latest.values() if status in (REJECTED, PARTIAL))


def to_out(db: Session, revs: list[SupplierPriceRevision], detail: bool = False) -> list[dict]:
    supplier_ids = {r.supplier_id for r in revs}
    user_ids = {r.sent_by for r in revs} | {r.responded_by for r in revs if r.responded_by}
    suppliers = {s.id: s.supplier_name for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()} if supplier_ids else {}
    users = {u.id: u.username for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    now = _now()
    cutoff = approval_cutoff(db)
    out = []
    for r in revs:
        responses = item_responses(r)
        row = {
            "id": r.id,
            "supplier_id": r.supplier_id,
            "supplier_name": suppliers.get(r.supplier_id, "—"),
            "delivery_date": r.delivery_date,
            "status": effective_status(r, cutoff, now),
            "item_count": len(r.items),
            "sent_at": r.sent_at,
            "sent_by_name": users.get(r.sent_by),
            "responded_at": r.responded_at,
            "responded_by_name": users.get(r.responded_by) if r.responded_by else None,
            "signer_name": r.signer_name,
            "rejection_reason": r.rejection_reason,
            "closed_reason": r.closed_reason,
            "expires_at": expires_at(r.delivery_date, cutoff),
            "approved_count": sum(1 for x in responses.values() if x["decision"] == APPROVED),
            "rejected_count": sum(1 for x in responses.values() if x["decision"] == REJECTED),
        }
        if detail:
            row.update(
                items=[
                    {
                        **i,
                        "decision": responses.get(i["supplier_price_id"], {}).get("decision"),
                        "counter_price": responses.get(i["supplier_price_id"], {}).get("counter_price"),
                    }
                    for i in r.items
                ],
                snapshot_hash=r.snapshot_hash,
                signature_image=r.signature_image,
                signer_ip=r.signer_ip,
                signer_user_agent=r.signer_user_agent,
            )
        out.append(row)
    return out
