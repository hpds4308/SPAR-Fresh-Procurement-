from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.core.audit import write_audit_log
from app.core.errors import ValidationFailedError
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.supplier import SupplierAccountUpdate, SupplierCreate, SupplierOut as SupplierDetailOut
from app.schemas.supplier_order import SupplierOut
from app.services import supplier_account_service, supplier_order_service

router = APIRouter(prefix="/suppliers", dependencies=[Depends(get_current_user)])


def _next_supplier_code(db: Session) -> str:
    """SUP01, SUP02, ... — matches seed_master_data.py's numbering."""
    existing = [c for (c,) in db.query(Supplier.supplier_code).all()]
    nums = [int(c[3:]) for c in existing if c.upper().startswith("SUP") and c[3:].isdigit()]
    next_num = (max(nums) + 1) if nums else 1
    return f"SUP{next_num:02d}"


@router.get("", response_model=list[SupplierOut])
def list_suppliers(admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Active suppliers, for populating pickers in the admin UI (e.g. the supplier order builder)."""
    return supplier_order_service.list_suppliers(db)


@router.get("/all", response_model=list[SupplierDetailOut])
def list_all_suppliers(admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Every supplier (active or not) with full contact details — for the Accounts page."""
    return db.query(Supplier).order_by(Supplier.supplier_name).all()


@router.get("/me/account", response_model=SupplierDetailOut)
def get_my_account(supplier_user: User = Depends(require_roles("SUPPLIER")), db: Session = Depends(get_db)):
    """The signed-in supplier's own Account details."""
    return supplier_account_service.get_my_account(db, supplier_user)


@router.put("/me/account", response_model=SupplierDetailOut)
def update_my_account(
    payload: SupplierAccountUpdate,
    supplier_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """Saves the supplier's name, company number, WhatsApp number and email — admins see them under Accounts."""
    return supplier_account_service.update_my_account(db, supplier_user, payload)


@router.post("", response_model=SupplierDetailOut)
def create_supplier(
    payload: SupplierCreate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Creates a new supplier master-data row — previously the only way a
    supplier entered the system at all was scripts/seed_master_data.py
    reading a CSV on the server. This is the first runtime create path.
    """
    supplier_code = (payload.supplier_code or _next_supplier_code(db)).strip().upper()
    supplier_name = payload.supplier_name.strip()

    if db.query(Supplier).filter(Supplier.supplier_code == supplier_code).first():
        raise ValidationFailedError(f"Supplier code '{supplier_code}' is already in use.")
    if db.query(Supplier).filter(Supplier.supplier_name == supplier_name).first():
        raise ValidationFailedError(f"A supplier named '{supplier_name}' already exists.")

    supplier = Supplier(
        supplier_code=supplier_code,
        supplier_name=supplier_name,
        contact_person=payload.contact_person.strip() if payload.contact_person else None,
        phone=payload.phone.strip() if payload.phone else None,
        email=payload.email.strip() if payload.email else None,
        address=payload.address.strip() if payload.address else None,
        status="ACTIVE",
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="SUPPLIER_CREATED",
        entity_type="supplier",
        entity_id=supplier.id,
        description=f"Created supplier '{supplier_name}' ({supplier_code}).",
    )
    return supplier
