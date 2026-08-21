from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.message import BranchThreadOut, MessageOut, MessageCreate, SupplierThreadOut, UnreadCountOut
from app.services import message_service

router = APIRouter(prefix="/messages", dependencies=[Depends(get_current_user)])


# ---- Admin side: one thread per supplier ----


@router.get("/admin/threads", response_model=list[SupplierThreadOut])
def admin_list_threads(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every active supplier, most recently-active thread first, with an unread count each."""
    return message_service.list_admin_threads(db)


@router.get("/admin/unread-count", response_model=UnreadCountOut)
def admin_unread_count(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return UnreadCountOut(count=message_service.admin_unread_count(db))


# ---- Admin side: one thread per branch ----
# (Declared before the /admin/{supplier_id} catch-all below — FastAPI
# matches routes in declaration order, so a literal path like
# /admin/branch-threads must come before a parameterized /admin/{supplier_id}
# or it gets swallowed as supplier_id="branch-threads" and 422s.)


@router.get("/admin/branch-threads", response_model=list[BranchThreadOut])
def admin_list_branch_threads(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every active branch, most recently-active thread first, with an unread count each."""
    return message_service.list_admin_branch_threads(db)


@router.get("/admin/branch/{branch_id}", response_model=list[MessageOut])
def admin_get_branch_thread(
    branch_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Opening a thread marks the branch's messages in it as read."""
    return message_service.list_for_admin_branch(db, branch_id)


@router.post("/admin/branch/{branch_id}", response_model=MessageOut)
def admin_send_branch_message(
    branch_id: int,
    payload: MessageCreate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return message_service.send_as_admin_to_branch(db, admin, branch_id, payload.body)


@router.get("/admin/{supplier_id}", response_model=list[MessageOut])
def admin_get_thread(
    supplier_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Opening a thread marks the supplier's messages in it as read."""
    return message_service.list_for_admin(db, supplier_id)


@router.post("/admin/{supplier_id}", response_model=MessageOut)
def admin_send_message(
    supplier_id: int,
    payload: MessageCreate,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return message_service.send_as_admin(db, admin, supplier_id, payload.body)


# ---- Supplier/Branch side: each only ever has one thread, with Admin ----


@router.get("/mine", response_model=list[MessageOut])
def my_thread(
    current_user: User = Depends(require_roles("SUPPLIER", "BRANCH")),
    db: Session = Depends(get_db),
):
    """Opening this marks Admin's messages as read."""
    if current_user.branch_id:
        return message_service.list_for_branch(db, current_user)
    return message_service.list_for_supplier(db, current_user)


@router.post("/mine", response_model=MessageOut)
def send_my_message(
    payload: MessageCreate,
    current_user: User = Depends(require_roles("SUPPLIER", "BRANCH")),
    db: Session = Depends(get_db),
):
    if current_user.branch_id:
        return message_service.send_as_branch(db, current_user, payload.body)
    return message_service.send_as_supplier(db, current_user, payload.body)


@router.get("/mine/unread-count", response_model=UnreadCountOut)
def my_unread_count(
    current_user: User = Depends(require_roles("SUPPLIER", "BRANCH")),
    db: Session = Depends(get_db),
):
    """Lightweight poll for a tab badge — does NOT mark anything read."""
    if current_user.branch_id:
        return UnreadCountOut(count=message_service.branch_unread_count(db, current_user))
    return UnreadCountOut(count=message_service.supplier_unread_count(db, current_user))
