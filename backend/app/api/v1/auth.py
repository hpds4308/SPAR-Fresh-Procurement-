from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, get_user_roles, decode_token, create_access_token
from app.core.audit import write_audit_log
from app.core.rate_limit import limiter
from app.models.user import User
from app.models.branch import Branch
from app.models.supplier import Supplier
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    RefreshRequest,
    ChangePasswordRequest,
    CurrentUserResponse,
)
from app.services import auth_service

router = APIRouter(prefix="/auth")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    access_token, refresh_token, role, redirect_to = auth_service.authenticate(
        db, payload.username, payload.password, ip_address=request.client.host if request.client else None
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        role=role,
        redirect_to=redirect_to,
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    user_id = decode_token(payload.refresh_token, expected_type="refresh")
    user = db.get(User, user_id)
    if not user or not user.is_active:
        from app.core.errors import UnauthorizedError

        raise UnauthorizedError("Account is inactive or does not exist.")
    roles = get_user_roles(db, user.id)
    primary_role = roles[0] if roles else ""
    access_token = create_access_token(user.id)
    return TokenResponse(
        access_token=access_token,
        refresh_token=payload.refresh_token,
        role=primary_role,
        redirect_to=auth_service.ROLE_REDIRECTS.get(primary_role, "/"),
    )


@router.post("/logout")
def logout(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    write_audit_log(db, user_id=current_user.id, role=None, action="LOGOUT", entity_type="user", entity_id=current_user.id)
    return {"detail": "Logged out."}


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    auth_service.change_password(db, current_user, payload.current_password, payload.new_password)
    return {"detail": "Password changed successfully."}


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = get_user_roles(db, current_user.id)
    role = roles[0] if roles else ""
    branch_name = None
    supplier_name = None
    if current_user.branch_id:
        branch = db.get(Branch, current_user.branch_id)
        branch_name = branch.branch_name if branch else None
    if current_user.supplier_id:
        supplier = db.get(Supplier, current_user.supplier_id)
        supplier_name = supplier.supplier_name if supplier else None
    return CurrentUserResponse(
        id=current_user.id,
        username=current_user.username,
        role=role,
        branch_id=current_user.branch_id,
        branch_name=branch_name,
        supplier_id=current_user.supplier_id,
        supplier_name=supplier_name,
    )
