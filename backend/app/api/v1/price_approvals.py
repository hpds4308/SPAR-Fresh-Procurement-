"""
Supplier approval (e-signature) of Admin's adjusted prices — see
price_approval_service.py for the full flow.
"""
from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.price_approval import (
    ApproveRevisionRequest,
    CountOut,
    RejectRevisionRequest,
    RevisionDetailOut,
    RevisionSummaryOut,
    SendForApprovalRequest,
)
from app.services import price_approval_service as svc

router = APIRouter(prefix="/price-approvals", dependencies=[Depends(get_current_user)])


def _client_ip(request: Request) -> str | None:
    # Behind Railway's/Caddy's proxy the socket peer is the proxy itself, so
    # the whole X-Forwarded-For chain is kept as-is (the client can prepend
    # to it, so no single hop is picked out as "the" address).
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.strip()
    return request.client.host if request.client else None


# ---- Admin ----


@router.post("/admin", response_model=RevisionDetailOut)
def send_for_approval(
    payload: SendForApprovalRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Sends every not-yet-agreed adjusted price for one supplier/delivery date as one sheet to sign."""
    rev = svc.send_for_approval(db, admin, payload.supplier_id, payload.delivery_date)
    return svc.to_out(db, [rev], detail=True)[0]


@router.get("/admin", response_model=list[RevisionSummaryOut])
def admin_list(
    delivery_date: date | None = None,
    supplier_id: int | None = None,
    status: str | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    revs = svc.list_revisions(db, supplier_id=supplier_id, delivery_date=delivery_date, status=status)
    return svc.to_out(db, revs)


@router.get("/admin/attention-count", response_model=CountOut)
def admin_attention_count(admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Rejected sheets for upcoming deliveries Admin hasn't followed up yet — the sidebar badge."""
    return CountOut(count=svc.admin_attention_count(db))


@router.get("/admin/{revision_id}", response_model=RevisionDetailOut)
def admin_get(revision_id: int, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    return svc.to_out(db, [svc.get_revision(db, revision_id)], detail=True)[0]


@router.post("/admin/{revision_id}/withdraw", response_model=RevisionDetailOut)
def admin_withdraw(revision_id: int, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    rev = svc.withdraw(db, admin, revision_id)
    return svc.to_out(db, [rev], detail=True)[0]


# ---- Supplier ----


@router.get("/mine", response_model=list[RevisionSummaryOut])
def my_list(current_user: User = Depends(require_roles("SUPPLIER")), db: Session = Depends(get_db)):
    if not current_user.supplier_id:
        return []
    revs = svc.list_revisions(db, supplier_id=current_user.supplier_id, limit=100)
    return svc.to_out(db, revs)


@router.get("/mine/pending-count", response_model=CountOut)
def my_pending_count(current_user: User = Depends(require_roles("SUPPLIER")), db: Session = Depends(get_db)):
    return CountOut(count=svc.supplier_pending_count(db, current_user))


@router.get("/mine/{revision_id}", response_model=RevisionDetailOut)
def my_get(revision_id: int, current_user: User = Depends(require_roles("SUPPLIER")), db: Session = Depends(get_db)):
    rev = svc.get_own_revision(db, current_user, revision_id)
    return svc.to_out(db, [rev], detail=True)[0]


@router.post("/mine/{revision_id}/approve", response_model=RevisionDetailOut)
@limiter.limit("10/minute")
def my_approve(
    revision_id: int,
    payload: ApproveRevisionRequest,
    request: Request,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """E-sign: agreement tick + drawn signature, against the exact sheet the supplier saw."""
    rev = svc.approve(
        db,
        current_user,
        revision_id,
        snapshot_hash=payload.snapshot_hash,
        signer_name=payload.signer_name,
        signature_image=payload.signature_image,
        password=payload.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return svc.to_out(db, [rev], detail=True)[0]


@router.post("/mine/{revision_id}/reject", response_model=RevisionDetailOut)
def my_reject(
    revision_id: int,
    payload: RejectRevisionRequest,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    rev = svc.reject(db, current_user, revision_id, snapshot_hash=payload.snapshot_hash, reason=payload.reason)
    return svc.to_out(db, [rev], detail=True)[0]
