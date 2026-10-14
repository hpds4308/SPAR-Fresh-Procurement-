from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ValidationFailedError
from app.core.security import require_roles
from app.core.audit import write_audit_log
from app.models.user import User
from app.core import email as email_core
from app.core.config import settings as env_settings
from app.models.supplier import Supplier
from app.schemas.settings import (
    EmailLogOut,
    EmailStatusOut,
    MasterDataEmailOut,
    SettingsOut,
    SettingUpdateRequest,
    TestEmailOut,
)
from app.services import notification_service, settings_service

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
        supplier_approval_deadline=values[settings_service.SUPPLIER_APPROVAL_DEADLINE],
        supplier_price_days=values[settings_service.SUPPLIER_PRICE_DAYS],
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


@router.get("/email-status", response_model=EmailStatusOut)
def email_status(admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Whether notification emails can go out, who gets them, and the latest ones sent."""
    provider = (
        "Brevo"
        if env_settings.BREVO_API_KEY and env_settings.EMAIL_FROM_ADDRESS
        else "SMTP" if env_settings.SMTP_HOST else None
    )
    missing = [
        s.supplier_name
        for s in db.query(Supplier).filter(Supplier.status == "ACTIVE").order_by(Supplier.supplier_name)
        if not (s.email or "").strip()
    ]
    return EmailStatusOut(
        configured=email_core.email_configured(),
        provider=provider,
        from_address=email_core.from_address() or None,
        admin_recipients=notification_service.admin_emails(db),
        suppliers_without_email=missing,
        recent=[EmailLogOut.model_validate(r, from_attributes=True) for r in notification_service.recent_log(db)],
    )


@router.post("/email-test", response_model=TestEmailOut)
def send_test_email(admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """Sends a test email to the signed-in Admin's own Account email."""
    return TestEmailOut(status=notification_service.send_test_email(db, admin))


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
        supplier_approval_deadline=values[settings_service.SUPPLIER_APPROVAL_DEADLINE],
        supplier_price_days=values[settings_service.SUPPLIER_PRICE_DAYS],
        support_phone=values[settings_service.SUPPORT_PHONE],
    )
