from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.supplier import SupplierAccountUpdate


def _own_supplier(db: Session, user: User) -> Supplier:
    supplier = db.get(Supplier, user.supplier_id) if user.supplier_id else None
    if not supplier:
        raise NotFoundError("This account isn't linked to a supplier.")
    return supplier


def get_my_account(db: Session, user: User) -> Supplier:
    return _own_supplier(db, user)


def update_my_account(db: Session, user: User, payload: SupplierAccountUpdate) -> Supplier:
    """
    Saves the supplier's own Account details (name, company number, WhatsApp,
    email). The name is the same master-data name admins see everywhere, so
    it must stay unique across suppliers.
    """
    supplier = _own_supplier(db, user)

    clash = (
        db.query(Supplier)
        .filter(Supplier.supplier_name == payload.supplier_name, Supplier.id != supplier.id)
        .first()
    )
    if clash:
        raise ValidationFailedError(f"Another supplier is already named '{payload.supplier_name}'.")

    old_name = supplier.supplier_name
    supplier.supplier_name = payload.supplier_name
    supplier.company_number = payload.company_number
    supplier.whatsapp_number = payload.whatsapp_number
    supplier.email = payload.email
    supplier.account_updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(supplier)

    renamed = f" (renamed from '{old_name}')" if old_name != supplier.supplier_name else ""
    write_audit_log(
        db,
        user_id=user.id,
        role="SUPPLIER",
        action="SUPPLIER_ACCOUNT_UPDATED",
        entity_type="supplier",
        entity_id=supplier.id,
        description=f"Supplier '{supplier.supplier_name}' updated their account details{renamed}.",
    )
    return supplier
