"""
DB-backed tests for the supplier's own Account page — name, company number,
WhatsApp number and email, saved on the supplier row admins read under Accounts.
"""
import pytest
from pydantic import ValidationError

from app.core.errors import NotFoundError, ValidationFailedError
from app.schemas.supplier import SupplierAccountUpdate
from app.services import supplier_account_service


def _payload(**overrides):
    data = dict(
        supplier_name="Green Valley Farms",
        company_number="PV 12345",
        whatsapp_number="+94 77 123 4567",
        email="Orders@GreenValley.lk",
    )
    data.update(overrides)
    return SupplierAccountUpdate(**data)


def test_update_saves_details_and_timestamp(db_session, make_user, make_supplier):
    supplier = make_supplier()
    user = make_user(role="SUPPLIER", supplier=supplier)

    out = supplier_account_service.update_my_account(db_session, user, _payload())

    assert out.id == supplier.id
    assert out.supplier_name == "Green Valley Farms"
    assert out.company_number == "PV 12345"
    assert out.whatsapp_number == "+94 77 123 4567"
    assert out.email == "orders@greenvalley.lk"
    assert out.account_updated_at is not None
    assert supplier_account_service.get_my_account(db_session, user).company_number == "PV 12345"


def test_name_must_stay_unique(db_session, make_user, make_supplier):
    make_supplier(supplier_name="Taken Name")
    user = make_user(role="SUPPLIER", supplier=make_supplier())

    with pytest.raises(ValidationFailedError):
        supplier_account_service.update_my_account(db_session, user, _payload(supplier_name="Taken Name"))


def test_keeping_own_name_is_allowed(db_session, make_user, make_supplier):
    supplier = make_supplier(supplier_name="Same Name")
    user = make_user(role="SUPPLIER", supplier=supplier)

    out = supplier_account_service.update_my_account(db_session, user, _payload(supplier_name="Same Name"))

    assert out.supplier_name == "Same Name"


def test_user_without_supplier_is_rejected(db_session, make_user):
    admin = make_user(role="ADMIN")

    with pytest.raises(NotFoundError):
        supplier_account_service.get_my_account(db_session, admin)


@pytest.mark.parametrize(
    "field,value",
    [
        ("supplier_name", "   "),
        ("company_number", ""),
        ("whatsapp_number", "abc"),
        ("email", "not-an-email"),
    ],
)
def test_invalid_input_rejected(field, value):
    with pytest.raises(ValidationError):
        _payload(**{field: value})
