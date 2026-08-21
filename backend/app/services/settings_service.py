"""
Admin-editable system settings, backed by the system_settings table.

Before this, BRANCH_ORDER_DEADLINE/SUPPLIER_PRICE_DEADLINE were .env-only —
changing them meant editing a file on the server and restarting the
backend container. This lets Admin change them (and the support contact
number, previously hardcoded in the Guidelines pages) from the UI, with
the .env values kept only as the first-run default until Admin overrides
them here.
"""
import re
from datetime import time

from sqlalchemy.orm import Session

from app.core.config import settings as env_settings
from app.core.errors import ValidationFailedError
from app.models.system import SystemSetting
from app.models.user import User

BRANCH_ORDER_DEADLINE = "branch_order_deadline"
SUPPLIER_PRICE_DEADLINE = "supplier_price_deadline"
SUPPORT_PHONE = "support_phone"

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _validate_time(value: str) -> None:
    if not _TIME_RE.match(value):
        raise ValidationFailedError("Time must be in HH:MM format, e.g. 14:00.")
    hh, mm = value.split(":")
    try:
        time(hour=int(hh), minute=int(mm))
    except ValueError:
        raise ValidationFailedError("That's not a valid time of day.")


def _validate_phone(value: str) -> None:
    if not value.strip():
        raise ValidationFailedError("Phone number can't be empty.")


# Each editable key: how to validate it, and where its first-run default
# comes from (the existing .env values — nothing changes for anyone who
# never opens the Settings page).
_KEYS = {
    BRANCH_ORDER_DEADLINE: (_validate_time, lambda: env_settings.BRANCH_ORDER_DEADLINE),
    SUPPLIER_PRICE_DEADLINE: (_validate_time, lambda: env_settings.SUPPLIER_PRICE_DEADLINE),
    SUPPORT_PHONE: (_validate_phone, lambda: "076 562 2317"),
}


def get_setting(db: Session, key: str) -> str:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        return row.value
    _, default_fn = _KEYS[key]
    return default_fn()


def get_all_settings(db: Session) -> dict[str, str]:
    return {key: get_setting(db, key) for key in _KEYS}


def set_setting(db: Session, admin: User, key: str, value: str) -> str:
    if key not in _KEYS:
        raise ValidationFailedError(f"Unknown setting: {key}")
    validate_fn, _ = _KEYS[key]
    value = value.strip()
    validate_fn(value)

    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
        row.updated_by = admin.id
    else:
        row = SystemSetting(key=key, value=value, updated_by=admin.id)
        db.add(row)
    db.commit()
    return value
