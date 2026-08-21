import pytest

from app.core.errors import ValidationFailedError
from app.services import settings_service
from tests.conftest import FakeDB


def test_valid_times_pass():
    settings_service._validate_time("14:00")
    settings_service._validate_time("00:00")
    settings_service._validate_time("23:59")
    settings_service._validate_time("9:05")  # single-digit hour is allowed


@pytest.mark.parametrize(
    "bad_value",
    ["25:00", "14:60", "not-a-time", "14", "14:00:00", ""],
)
def test_invalid_times_rejected(bad_value):
    with pytest.raises(ValidationFailedError):
        settings_service._validate_time(bad_value)


def test_blank_phone_rejected():
    with pytest.raises(ValidationFailedError):
        settings_service._validate_phone("   ")


def test_get_setting_falls_back_to_env_default_when_unset():
    db = FakeDB()
    # No row exists (FakeDB always returns None), so this must return the
    # .env-configured default rather than raising or returning None —
    # this is the exact behavior that keeps a fresh install working
    # without anyone having to touch the Settings page first.
    value = settings_service.get_setting(db, settings_service.BRANCH_ORDER_DEADLINE)
    assert value  # a real HH:MM string, not empty/None
    settings_service._validate_time(value)


def test_set_setting_rejects_unknown_key():
    db = FakeDB()
    with pytest.raises(ValidationFailedError):
        settings_service.set_setting(db, admin=None, key="not_a_real_setting", value="x")
