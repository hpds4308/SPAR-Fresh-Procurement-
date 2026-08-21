from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles
from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError
from app.models.branch import Branch
from app.models.user import User
from app.schemas.branch import BranchOut, BranchCreate

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
