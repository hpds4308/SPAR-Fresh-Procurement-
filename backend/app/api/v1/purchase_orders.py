"""
Purchase orders Admin issues to suppliers — see purchase_order_service.py.
"""
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.purchase_order import (
    IssuePurchaseOrderRequest,
    PurchaseOrderAdminRowOut,
    PurchaseOrderDetailOut,
    PurchaseOrderSummaryOut,
)
from app.services import purchase_order_service as svc

router = APIRouter(prefix="/purchase-orders", dependencies=[Depends(get_current_user)])


# ---- Admin ----


@router.get("/admin/dates", response_model=list[date])
def admin_dates(admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return svc.list_purchase_order_dates(db)


@router.get("/admin", response_model=list[PurchaseOrderAdminRowOut])
def admin_list(
    delivery_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """One row per supplier with an order on this date, with its PO (if issued)."""
    return svc.list_admin_rows(db, delivery_date)


@router.post("/admin", response_model=PurchaseOrderDetailOut)
def admin_issue(
    payload: IssuePurchaseOrderRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Issues (or re-issues, as the next revision) the PO for a supplier's saved order on this date."""
    po = svc.issue_purchase_order(db, admin, payload.supplier_id, payload.delivery_date)
    return svc.to_detail(db, po, include_outdated=True)


@router.get("/admin/{po_id}", response_model=PurchaseOrderDetailOut)
def admin_get(po_id: int, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return svc.to_detail(db, svc.get_purchase_order(db, po_id), include_outdated=True)


@router.post("/admin/{po_id}/cancel", response_model=PurchaseOrderDetailOut)
def admin_cancel(po_id: int, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return svc.to_detail(db, svc.cancel_purchase_order(db, admin, po_id), include_outdated=True)


# ---- Supplier ----


@router.get("/mine", response_model=list[PurchaseOrderSummaryOut])
def my_list(current_user: User = Depends(require_roles("SUPPLIER")), db: Session = Depends(get_db)):
    return svc.list_my_purchase_orders(db, current_user)


@router.get("/mine/{po_id}", response_model=PurchaseOrderDetailOut)
def my_get(po_id: int, current_user: User = Depends(require_roles("SUPPLIER")), db: Session = Depends(get_db)):
    return svc.to_detail(db, svc.get_my_purchase_order(db, current_user, po_id))


# ---- Branch ----


@router.get("/branch", response_model=list[PurchaseOrderSummaryOut])
def branch_list(current_user: User = Depends(require_roles("BRANCH")), db: Session = Depends(get_db)):
    """This branch's own branch POs, from every supplier."""
    return svc.list_branch_purchase_orders(db, current_user)


@router.get("/branch/{po_id}", response_model=PurchaseOrderDetailOut)
def branch_get(po_id: int, current_user: User = Depends(require_roles("BRANCH")), db: Session = Depends(get_db)):
    return svc.get_branch_purchase_order(db, current_user, po_id)
