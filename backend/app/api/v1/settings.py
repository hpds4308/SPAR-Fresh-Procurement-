from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ValidationFailedError
from app.core.security import require_roles
from app.core.audit import write_audit_log
from app.models.user import User
from app.schemas.settings import SettingsOut, SettingUpdateRequest, MasterDataEmailOut
from app.services import settings_service

router = APIRouter(prefix="/settings")


@router.get("", response_model=SettingsOut)
def get_settings(db: Session = Depends(get_db)):
    """
    Deliberately public, no login required — cutoff times and the
    support number are shown on Branch/Supplier/Admin screens, but the
    support number specifically also needs to reach someone who's locked
    out and can't log in at all, on the login page itself. None of this
    is sensitive.
    """
    values = settings_service.get_all_settings(db)
    return SettingsOut(
        branch_order_deadline=values[settings_service.BRANCH_ORDER_DEADLINE],
        supplier_price_deadline=values[settings_service.SUPPLIER_PRICE_DEADLINE],
        support_phone=values[settings_service.SUPPORT_PHONE],
    )


@router.get("/master-data-email", response_model=MasterDataEmailOut)
def get_master_data_email(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """The address "Send to Master Data" (Master Data Sheet page) emails the
    Excel export to. Admin-only, so it stays off the public GET /settings."""
    return MasterDataEmailOut(
        master_data_email=settings_service.get_setting(db, settings_service.MASTER_DATA_EMAIL)
    )


@router.put("/master-data-email", response_model=MasterDataEmailOut)
def update_master_data_email(
    payload: SettingUpdateRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    settings_service.set_setting(db, admin, settings_service.MASTER_DATA_EMAIL, payload.value)
    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="SETTING_UPDATED",
        entity_type="system_setting",
        entity_id=None,
        description=f"Set {settings_service.MASTER_DATA_EMAIL} = {payload.value}",
    )
    return MasterDataEmailOut(
        master_data_email=settings_service.get_setting(db, settings_service.MASTER_DATA_EMAIL)
    )


@router.put("/{key}", response_model=SettingsOut)
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    if key == settings_service.MASTER_DATA_EMAIL:
        # It isn't part of the public SettingsOut shape this endpoint returns.
        raise ValidationFailedError("Use PUT /settings/master-data-email for that setting.")
    settings_service.set_setting(db, admin, key, payload.value)
    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="SETTING_UPDATED",
        entity_type="system_setting",
        entity_id=None,
        description=f"Set {key} = {payload.value}",
    )
    values = settings_service.get_all_settings(db)
    return SettingsOut(
        branch_order_deadline=values[settings_service.BRANCH_ORDER_DEADLINE],
        supplier_price_deadline=values[settings_service.SUPPLIER_PRICE_DEADLINE],
        support_phone=values[settings_service.SUPPORT_PHONE],
    )
