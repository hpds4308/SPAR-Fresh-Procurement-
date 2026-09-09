from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError, NotFoundError
from app.models.branch import Branch
from app.models.user import User
from app.schemas.branch import BranchOut, BranchCreate, BranchPosLocationCodeUpdate
from app.schemas.order import OrderDeadlineExceptionRequest, OrderDeadlineExceptionOut
from app.services import order_service

router = APIRouter(prefix="/branches", dependencies=[Depends(require_roles("ADMIN"))])


def _next_branch_code(db: Session) -> str:
    """BR01, BR02, ... — matches seed_master_data.py's numbering. Falls
    back past 2 digits automatically (BR100) rather than colliding once
    there are 100+ branches."""
    existing = [c for (c,) in db.query(Branch.branch_code).all()]
    nums = [int(c[2:]) for c in existing if c.upper().startswith("BR") and c[2:].isdigit()]
    next_num = (max(nums) + 1) if nums else 1
    return f"BR{next_num:02d}"


@router.get("", response_model=list[BranchOut])
def list_branches(db: Session = Depends(get_db)):
    """Every branch (active or not) — the Accounts page needs to see
    inactive ones too, not just the active-only picker in users.py."""
    return db.query(Branch).order_by(Branch.branch_name).all()


@router.post("", response_model=BranchOut)
def create_branch(
    payload: BranchCreate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Creates a new branch master-data row — previously the only way a
    branch entered the system at all was scripts/seed_master_data.py
    reading a CSV on the server. This is the first runtime create path.
    """
    branch_code = (payload.branch_code or _next_branch_code(db)).strip().upper()
    branch_name = payload.branch_name.strip()

    if db.query(Branch).filter(Branch.branch_code == branch_code).first():
        raise ValidationFailedError(f"Branch code '{branch_code}' is already in use.")
    if db.query(Branch).filter(Branch.branch_name == branch_name).first():
        raise ValidationFailedError(f"A branch named '{branch_name}' already exists.")

    branch = Branch(
        branch_code=branch_code,
        branch_name=branch_name,
        location=payload.location.strip() if payload.location else None,
        status="ACTIVE",
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="BRANCH_CREATED",
        entity_type="branch",
        entity_id=branch.id,
        description=f"Created branch '{branch_name}' ({branch_code}).",
    )
    return branch


@router.patch("/{branch_id}/pos-location-code", response_model=BranchOut)
def set_branch_pos_location_code(
    branch_id: int,
    payload: BranchPosLocationCodeUpdate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Sets the branch's location code in the 24X7Retail/Dynamic Web POS
    system — needed for the stock-in-hand lookup on the branch's New
    Order page. A separate value from branch_code; look it up from the
    POS system's own location list, don't assume it matches.
    """
    branch = db.get(Branch, branch_id)
    if not branch:
        raise NotFoundError("Branch not found.")

    value = payload.pos_location_code.strip() if payload.pos_location_code else None
    branch.pos_location_code = value
    db.commit()
    db.refresh(branch)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="BRANCH_POS_LOCATION_CODE_SET",
        entity_type="branch",
        entity_id=branch.id,
        description=f"Set POS location code for '{branch.branch_name}' to {value or '(cleared)'}.",
    )
    return branch


@router.get("/order-deadline-exceptions", response_model=list[OrderDeadlineExceptionOut])
def list_order_deadline_exceptions(
    order_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every branch currently allowed to submit an order past the normal
    cutoff for one order_date — usually today, so Admin can see at a
    glance who's already been given an exception before granting another."""
    return order_service.list_deadline_exceptions(db, order_date)


@router.post("/{branch_id}/order-deadline-exception")
def grant_order_deadline_exception(
    branch_id: int,
    payload: OrderDeadlineExceptionRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Lets this one branch submit (or keep editing) its order for
    payload.order_date past today's normal cutoff — a one-time exception,
    not a change to the cutoff itself. Idempotent: granting an exception
    that already exists is a no-op.
    """
    order_service.grant_late_submission(db, admin, branch_id, payload.order_date)
    return {"detail": "Late submission allowed for this branch and date."}


@router.delete("/{branch_id}/order-deadline-exception")
def revoke_order_deadline_exception(
    branch_id: int,
    order_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Withdraws a previously-granted late-submission exception. Safe to call even if none exists."""
    order_service.revoke_late_submission(db, admin, branch_id, order_date)
    return {"detail": "Late submission exception withdrawn."}
