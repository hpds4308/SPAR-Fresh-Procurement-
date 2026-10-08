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
# Weekdays suppliers may submit prices on, stored as comma-separated
# date.weekday() numbers (Monday=0 .. Sunday=6), e.g. "0,2,4".
SUPPLIER_PRICE_DAYS = "supplier_price_days"
SUPPORT_PHONE = "support_phone"
MASTER_DATA_EMAIL = "master_data_email"

_TIME_RE = re.compile(r"^\d{1,2}:\d{2}$")
# Deliberately loose — just enough to catch obvious typos (missing @,
# missing domain dot). Real deliverability is proven by the first send.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_time(value: str) -> None:
    if not _TIME_RE.match(value):
        raise ValidationFailedError("Time must be in HH:MM format, e.g. 14:00.")
    hh, mm = value.split(":")
    try:
        time(hour=int(hh), minute=int(mm))
    except ValueError:
        raise ValidationFailedError("That's not a valid time of day.")


WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def parse_weekdays(value: str) -> list[int]:
    """"0,2,4" -> [0, 2, 4]: sorted, de-duplicated, each 0..6, at least one."""
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if not parts or not all(p.isdigit() and 0 <= int(p) <= 6 for p in parts):
        raise ValidationFailedError("Choose at least one day of the week.")
    return sorted({int(p) for p in parts})


def weekdays_label(weekdays: list[int]) -> str:
    """[0, 2, 4] -> "Monday, Wednesday and Friday"."""
    names = [WEEKDAY_NAMES[d] for d in weekdays]
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _validate_weekdays(value: str) -> str:
    return ",".join(str(d) for d in parse_weekdays(value))


def _validate_phone(value: str) -> None:
    if not value.strip():
        raise ValidationFailedError("Phone number can't be empty.")


def _validate_email(value: str) -> None:
    if not _EMAIL_RE.match(value.strip()):
        raise ValidationFailedError("Enter a valid email address, e.g. name@example.com.")


# Each editable key: how to validate it, and where its first-run default
# comes from (the existing .env values — nothing changes for anyone who
# never opens the Settings page).
_KEYS = {
    BRANCH_ORDER_DEADLINE: (_validate_time, lambda: env_settings.BRANCH_ORDER_DEADLINE),
    SUPPLIER_PRICE_DEADLINE: (_validate_time, lambda: env_settings.SUPPLIER_PRICE_DEADLINE),
    # Monday, Wednesday and Friday — the rule as originally agreed with the client.
    SUPPLIER_PRICE_DAYS: (_validate_weekdays, lambda: "0,2,4"),
    SUPPORT_PHONE: (_validate_phone, lambda: "076 562 2317"),
    # No first-run default — "Send to Master Data" stays disabled with a
    # clear message until Admin sets a real address on the Settings page.
    MASTER_DATA_EMAIL: (_validate_email, lambda: ""),
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
    # A validator may hand back a normalized form to store (e.g. weekdays
    # "4,0,2,2" -> "0,2,4"); the rest just raise on bad input.
    value = validate_fn(value) or value

    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row:
        row.value = value
        row.updated_by = admin.id
    else:
        row = SystemSetting(key=key, value=value, updated_by=admin.id)
        db.add(row)
    db.commit()
    return value
