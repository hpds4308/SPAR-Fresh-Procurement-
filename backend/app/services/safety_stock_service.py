from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError, ValidationFailedError
from app.models.product import Product
from app.models.safety_stock import BranchSafetyStock
from app.models.user import User
from app.schemas.safety_stock import SafetyStockOut, SafetyStockSave


def _require_branch(branch_user: User) -> int:
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts have a safety stock list.")
    return branch_user.branch_id


def get_for_branch(db: Session, branch_user: User) -> SafetyStockOut:
    branch_id = _require_branch(branch_user)
    rows = db.query(BranchSafetyStock).filter(BranchSafetyStock.branch_id == branch_id).all()
    latest = max(rows, key=lambda r: r.updated_at, default=None)
    updated_by = db.get(User, latest.updated_by) if latest else None
    return SafetyStockOut(
        quantities={r.product_id: float(r.quantity) for r in rows},
        updated_at=latest.updated_at if latest else None,
        updated_by_username=updated_by.username if updated_by else None,
    )


def save_for_branch(db: Session, branch_user: User, payload: SafetyStockSave) -> SafetyStockOut:
    """
    Replaces the branch's whole safety-stock list with payload.lines. Rows
    persist across days — nothing here is date-scoped — so the saved
    figures stay until the branch saves again or clears them.
    """
    branch_id = _require_branch(branch_user)

    wanted = {ln.product_id: ln.quantity for ln in payload.lines}
    if len(wanted) != len(payload.lines):
        raise ValidationFailedError("Each product can only appear once.")
    if wanted:
        found = {
            pid
            for (pid,) in db.query(Product.id).filter(Product.id.in_(wanted.keys()), Product.status == "ACTIVE").all()
        }
        missing = set(wanted) - found
        if missing:
            raise ValidationFailedError(f"Unknown or inactive product id(s): {sorted(missing)}")

    existing = {
        r.product_id: r
        for r in db.query(BranchSafetyStock).filter(BranchSafetyStock.branch_id == branch_id).all()
    }
    for pid, row in existing.items():
        if pid not in wanted:
            db.delete(row)
    for pid, qty in wanted.items():
        row = existing.get(pid)
        if row is None:
            db.add(BranchSafetyStock(branch_id=branch_id, product_id=pid, quantity=qty, updated_by=branch_user.id))
        elif float(row.quantity) != qty:
            row.quantity = qty
            row.updated_by = branch_user.id
            row.updated_at = func.now()
    db.commit()
    return get_for_branch(db, branch_user)
