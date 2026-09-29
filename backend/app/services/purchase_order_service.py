"""
Purchase orders: the formal, numbered document Admin issues to a supplier
once their order for a delivery date has been built and saved on Supplier
Orders (supplier_order_service).

Issuing freezes that saved order — every branch line with its resolved
price — into a PurchaseOrder snapshot. The PO comes in two views, both
derived from the same snapshot:
  - the supplier PO   PO-<yymmdd>-<supplier_code>: all branches combined
  - a branch PO each  PO-<yymmdd>-<supplier_code>-<branch_code>: what that
                      one branch should receive

Editing the supplier order afterwards doesn't touch the issued PO; it's
reported as out of date until Admin re-issues it (same number, next
revision). Every line must have a price before a PO can be issued.
"""
import hashlib
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.models.branch import Branch
from app.models.purchase_order import PurchaseOrder
from app.models.supplier import Supplier
from app.models.supplier_order import SupplierOrderItem
from app.models.user import User
from app.schemas.purchase_order import (
    BranchPurchaseOrderOut,
    PurchaseOrderAdminRowOut,
    PurchaseOrderDetailOut,
    PurchaseOrderLineOut,
    PurchaseOrderSummaryOut,
    PurchaseOrderSupplierOut,
)
from app.services import supplier_order_service


def _code_part(code: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", code).upper()


def _po_number(supplier: Supplier, delivery_date: date) -> str:
    return f"PO-{delivery_date:%y%m%d}-{_code_part(supplier.supplier_code)}"


def _branch_po_number(po_number: str, branch_code: str) -> str:
    return f"{po_number}-{_code_part(branch_code)}"


def _current_lines(db: Session, supplier_id: int, delivery_date: date) -> list[dict]:
    """The supplier's saved order for this date as snapshot lines, priced
    exactly as Supplier Orders shows them (agreed price, else the resolved
    quote). unit_price is None for a line with no price anywhere yet."""
    order = supplier_order_service.get_supplier_order(db, supplier_id, delivery_date)
    branch_ids = {it.branch_id for it in order.items}
    branches = {b.id: b for b in db.query(Branch).filter(Branch.id.in_(branch_ids)).all()} if branch_ids else {}
    lines = []
    for it in order.items:
        branch = branches.get(it.branch_id)
        lines.append(
            {
                "branch_id": it.branch_id,
                "branch_code": branch.branch_code if branch else "—",
                "branch_name": it.branch_name,
                "branch_location": branch.location if branch else None,
                "product_id": it.product_id,
                "product_code": it.product_code,
                "product_description": it.product_description,
                "unit_code": it.unit_code,
                "quantity": it.quantity,
                "unit_price": it.effective_price,
                "line_total": it.line_total,
                "price_is_estimated": it.price_is_estimated,
                "notes": it.notes,
            }
        )
    lines.sort(key=lambda ln: (ln["branch_name"], ln["product_description"]))
    return lines


def _hash_lines(lines: list[dict]) -> str:
    """Fingerprint of what the PO commits to — quantities, units, prices
    and notes per branch/product. Names are left out so renaming a product
    or branch doesn't mark every PO that mentions it as out of date."""
    canonical = sorted(
        (ln["branch_id"], ln["product_id"], ln["unit_code"], ln["quantity"], ln["unit_price"], ln["notes"] or "")
        for ln in lines
    )
    return hashlib.sha256(json.dumps(canonical, separators=(",", ":")).encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_purchase_order(db: Session, admin: User, supplier_id: int, delivery_date: date) -> PurchaseOrder:
    supplier = db.get(Supplier, supplier_id)
    if not supplier:
        raise NotFoundError("Supplier not found.")

    lines = _current_lines(db, supplier_id, delivery_date)
    if not lines:
        raise ValidationFailedError(
            f"{supplier.supplier_name} has no order saved for this delivery date. "
            "Build and save their order on Supplier Orders first."
        )
    unpriced = [ln for ln in lines if ln["unit_price"] is None]
    if unpriced:
        names = sorted({f'{ln["product_description"]} ({ln["branch_name"]})' for ln in unpriced})
        shown = ", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else "")
        raise ValidationFailedError(
            f"{len(unpriced)} line(s) have no price yet: {shown}. "
            "Set an agreed price for them on Supplier Orders before issuing the PO."
        )

    total = round(sum(ln["line_total"] for ln in lines), 2)
    snapshot_hash = _hash_lines(lines)

    po = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.supplier_id == supplier_id, PurchaseOrder.delivery_date == delivery_date)
        .first()
    )
    if po is None:
        po = PurchaseOrder(
            po_number=_po_number(supplier, delivery_date),
            supplier_id=supplier_id,
            delivery_date=delivery_date,
            revision=1,
        )
        db.add(po)
        action = "PURCHASE_ORDER_ISSUED"
    else:
        if po.status == "ISSUED" and po.snapshot_hash == snapshot_hash:
            # Nothing changed — re-issuing would only bump the revision.
            return po
        po.revision += 1
        action = "PURCHASE_ORDER_REISSUED"

    po.status = "ISSUED"
    po.items = lines
    po.total_amount = total
    po.snapshot_hash = snapshot_hash
    po.issued_by = admin.id
    po.issued_at = _now()
    po.cancelled_by = None
    po.cancelled_at = None
    db.commit()
    db.refresh(po)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action=action,
        entity_type="purchase_order",
        entity_id=po.id,
        description=(
            f"{po.po_number} rev {po.revision} for {supplier.supplier_name}, delivery "
            f"{delivery_date.isoformat()}: {len(lines)} line(s), Rs. {total:,.2f}."
        ),
    )
    return po


def cancel_purchase_order(db: Session, admin: User, po_id: int) -> PurchaseOrder:
    po = get_purchase_order(db, po_id)
    if po.status == "CANCELLED":
        raise ValidationFailedError("This purchase order is already cancelled.")
    po.status = "CANCELLED"
    po.cancelled_by = admin.id
    po.cancelled_at = _now()
    db.commit()
    db.refresh(po)
    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PURCHASE_ORDER_CANCELLED",
        entity_type="purchase_order",
        entity_id=po.id,
        description=f"{po.po_number} rev {po.revision} cancelled.",
    )
    return po


def get_purchase_order(db: Session, po_id: int) -> PurchaseOrder:
    po = db.get(PurchaseOrder, po_id)
    if not po:
        raise NotFoundError("Purchase order not found.")
    return po


def get_my_purchase_order(db: Session, supplier_user: User, po_id: int) -> PurchaseOrder:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts have purchase orders.")
    po = db.get(PurchaseOrder, po_id)
    # Same 404 whether it doesn't exist or belongs to another supplier.
    if not po or po.supplier_id != supplier_user.supplier_id:
        raise NotFoundError("Purchase order not found.")
    return po


def list_my_purchase_orders(db: Session, supplier_user: User) -> list[PurchaseOrderSummaryOut]:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts have purchase orders.")
    pos = (
        db.query(PurchaseOrder)
        .filter(PurchaseOrder.supplier_id == supplier_user.supplier_id)
        .order_by(PurchaseOrder.delivery_date.desc(), PurchaseOrder.id.desc())
        .limit(200)
        .all()
    )
    return to_summaries(db, pos)


def _branch_id_of(user: User) -> int:
    if not user.branch_id:
        raise PermissionDeniedError("Only branch accounts have branch purchase orders.")
    return user.branch_id


def _for_branch(detail: PurchaseOrderDetailOut, branch_id: int) -> PurchaseOrderDetailOut:
    """Cuts a PO down to one branch's own branch PO — a branch never sees
    other branches' quantities or the supplier's combined total."""
    branch = next(b for b in detail.branches if b.branch_id == branch_id)
    return detail.model_copy(
        update={
            "po_number": branch.po_number,
            "branch_count": 1,
            "line_count": len(branch.lines),
            "total_amount": branch.total,
            "consolidated_lines": branch.lines,
            "branches": [branch],
            "is_outdated": False,
        }
    )


def list_branch_purchase_orders(db: Session, branch_user: User, q: str | None = None) -> list[PurchaseOrderSummaryOut]:
    """Every PO with lines for this branch, as that branch's own branch PO,
    most recent delivery first. `q` searches ALL of the branch's POs (not
    just the recent ones listed by default) by branch PO number or supplier
    name; punctuation and case are ignored, so "261001sup01br02" finds
    PO-261001-SUP01-BR02."""
    branch_id = _branch_id_of(branch_user)
    needle = _code_part(q or "")
    query = db.query(PurchaseOrder).order_by(PurchaseOrder.delivery_date.desc(), PurchaseOrder.id.desc())
    if not needle:
        query = query.limit(1000)
    suppliers = {s.id: _code_part(s.supplier_name) for s in db.query(Supplier).all()} if needle else {}

    matched = []
    limit = 50 if needle else 200
    for po in query.all():
        # items is plain JSON (not JSONB), so the branch filter runs here.
        own = next((ln for ln in po.items if ln["branch_id"] == branch_id), None)
        if own is None:
            continue
        if needle:
            branch_number = _code_part(_branch_po_number(po.po_number, own["branch_code"]))
            if needle not in branch_number and needle not in suppliers.get(po.supplier_id, ""):
                continue
        matched.append(po)
        if len(matched) >= limit:
            break
    pos = matched
    return [
        PurchaseOrderSummaryOut(**_for_branch(to_detail(db, po), branch_id).model_dump(include=set(PurchaseOrderSummaryOut.model_fields)))
        for po in pos
    ]


def get_branch_purchase_order(db: Session, branch_user: User, po_id: int) -> PurchaseOrderDetailOut:
    branch_id = _branch_id_of(branch_user)
    po = db.get(PurchaseOrder, po_id)
    # Same 404 whether it doesn't exist or has nothing for this branch.
    if not po or not any(ln["branch_id"] == branch_id for ln in po.items):
        raise NotFoundError("Purchase order not found.")
    return _for_branch(to_detail(db, po), branch_id)


def list_admin_rows(db: Session, delivery_date: date) -> list[PurchaseOrderAdminRowOut]:
    """Every supplier with an order saved for this date, plus any PO on
    this date whose supplier order has since been emptied — each with its
    PO status, so Admin can see at a glance what's still to be issued."""
    order_supplier_ids = {
        r[0]
        for r in db.query(SupplierOrderItem.supplier_id)
        .filter(SupplierOrderItem.delivery_date == delivery_date)
        .distinct()
        .all()
    }
    pos = {po.supplier_id: po for po in db.query(PurchaseOrder).filter(PurchaseOrder.delivery_date == delivery_date).all()}
    supplier_ids = order_supplier_ids | set(pos.keys())
    if not supplier_ids:
        return []
    suppliers = {s.id: s for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}
    summaries = {s.supplier_id: s for s in to_summaries(db, list(pos.values()))}

    rows = []
    for supplier_id in supplier_ids:
        lines = _current_lines(db, supplier_id, delivery_date) if supplier_id in order_supplier_ids else []
        po = pos.get(supplier_id)
        rows.append(
            PurchaseOrderAdminRowOut(
                supplier_id=supplier_id,
                supplier_name=suppliers[supplier_id].supplier_name if supplier_id in suppliers else "—",
                delivery_date=delivery_date,
                line_count=len(lines),
                order_total=round(sum(ln["line_total"] or 0 for ln in lines), 2),
                unpriced_line_count=sum(1 for ln in lines if ln["unit_price"] is None),
                purchase_order=summaries.get(supplier_id),
                is_outdated=po is not None and po.status == "ISSUED" and po.snapshot_hash != _hash_lines(lines),
            )
        )
    rows.sort(key=lambda r: r.supplier_name.lower())
    return rows


def list_purchase_order_dates(db: Session) -> list[date]:
    """Dates with a saved supplier order or an issued PO, most recent first."""
    dates = {r[0] for r in db.query(SupplierOrderItem.delivery_date).distinct().all()}
    dates |= {r[0] for r in db.query(PurchaseOrder.delivery_date).distinct().all()}
    return sorted(dates, reverse=True)


def _user_names(db: Session, pos: list[PurchaseOrder]) -> dict[int, str]:
    user_ids = {po.issued_by for po in pos}
    if not user_ids:
        return {}
    return {u.id: u.username for u in db.query(User).filter(User.id.in_(user_ids)).all()}


def _summary(po: PurchaseOrder, supplier_name: str, issued_by_name: str | None) -> dict:
    return {
        "id": po.id,
        "po_number": po.po_number,
        "revision": po.revision,
        "status": po.status,
        "supplier_id": po.supplier_id,
        "supplier_name": supplier_name,
        "delivery_date": po.delivery_date,
        "branch_count": len({ln["branch_id"] for ln in po.items}),
        "line_count": len(po.items),
        "total_amount": float(po.total_amount),
        "issued_at": po.issued_at,
        "issued_by_name": issued_by_name,
        "cancelled_at": po.cancelled_at,
    }


def to_summaries(db: Session, pos: list[PurchaseOrder]) -> list[PurchaseOrderSummaryOut]:
    supplier_ids = {po.supplier_id for po in pos}
    suppliers = (
        {s.id: s.supplier_name for s in db.query(Supplier).filter(Supplier.id.in_(supplier_ids)).all()}
        if supplier_ids
        else {}
    )
    users = _user_names(db, pos)
    return [
        PurchaseOrderSummaryOut(**_summary(po, suppliers.get(po.supplier_id, "—"), users.get(po.issued_by)))
        for po in pos
    ]


def _line_out(ln: dict) -> PurchaseOrderLineOut:
    return PurchaseOrderLineOut(
        product_id=ln["product_id"],
        product_code=ln["product_code"],
        product_description=ln["product_description"],
        unit_code=ln["unit_code"],
        quantity=ln["quantity"],
        unit_price=ln["unit_price"],
        line_total=ln["line_total"],
        price_is_estimated=ln.get("price_is_estimated", False),
        notes=ln.get("notes"),
    )


def _consolidate(lines: list[dict]) -> list[PurchaseOrderLineOut]:
    """One line per product across all branches. A product priced
    differently for different branches (per-line agreed price) stays as a
    separate line per price, so every line still reads qty x price = total."""
    grouped: dict[tuple, dict] = {}
    for ln in lines:
        key = (ln["product_id"], ln["unit_code"], ln["unit_price"])
        g = grouped.get(key)
        if g is None:
            grouped[key] = {**ln, "notes": None}
        else:
            g["quantity"] = round(g["quantity"] + ln["quantity"], 2)
            g["line_total"] = round(g["line_total"] + ln["line_total"], 2)
            g["price_is_estimated"] = g["price_is_estimated"] or ln.get("price_is_estimated", False)
    return [_line_out(g) for g in sorted(grouped.values(), key=lambda g: (g["product_description"], g["unit_price"]))]


def to_detail(db: Session, po: PurchaseOrder, include_outdated: bool = False) -> PurchaseOrderDetailOut:
    supplier = db.get(Supplier, po.supplier_id)
    users = _user_names(db, [po])

    by_branch: dict[int, list[dict]] = defaultdict(list)
    for ln in po.items:
        by_branch[ln["branch_id"]].append(ln)
    branches = []
    for branch_id, lines in by_branch.items():
        first = lines[0]
        branches.append(
            BranchPurchaseOrderOut(
                branch_id=branch_id,
                branch_code=first["branch_code"],
                branch_name=first["branch_name"],
                branch_location=first.get("branch_location"),
                po_number=_branch_po_number(po.po_number, first["branch_code"]),
                lines=[_line_out(ln) for ln in sorted(lines, key=lambda ln: ln["product_description"])],
                total=round(sum(ln["line_total"] for ln in lines), 2),
            )
        )
    branches.sort(key=lambda b: b.branch_name)

    is_outdated = False
    if include_outdated and po.status == "ISSUED":
        is_outdated = po.snapshot_hash != _hash_lines(_current_lines(db, po.supplier_id, po.delivery_date))

    return PurchaseOrderDetailOut(
        **_summary(po, supplier.supplier_name if supplier else "—", users.get(po.issued_by)),
        supplier=PurchaseOrderSupplierOut(
            supplier_id=po.supplier_id,
            supplier_code=supplier.supplier_code if supplier else "—",
            supplier_name=supplier.supplier_name if supplier else "—",
            contact_person=supplier.contact_person if supplier else None,
            phone=supplier.phone if supplier else None,
            email=supplier.email if supplier else None,
            address=supplier.address if supplier else None,
            company_number=supplier.company_number if supplier else None,
        ),
        consolidated_lines=_consolidate(po.items),
        branches=branches,
        is_outdated=is_outdated,
    )
