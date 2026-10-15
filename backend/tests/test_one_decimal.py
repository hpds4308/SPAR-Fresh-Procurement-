"""
Supplier prices and branch order quantities may only use one decimal
place — the second decimal must be 0 (5.70 is fine, 5.71 isn't). See
one_decimal_error in app/schemas/_limits.py.
"""
import pytest
from pydantic import ValidationError

from app.schemas.order import OrderLineCreate
from app.schemas.pricing import PriceEntry
from app.services.pricing_service import _parse_excel_price


@pytest.mark.parametrize("value", [5, 5.7, 5.70, 0.1, 1250, 1250.5, "5.60"])
def test_one_decimal_values_are_accepted(value):
    assert PriceEntry(product_id=1, price=value).price == round(float(value), 2)
    assert OrderLineCreate(product_id=1, quantity=value).quantity == round(float(value), 2)


@pytest.mark.parametrize("value", [5.71, 5.05, 0.01, 99.99])
def test_second_decimal_other_than_zero_is_refused(value):
    with pytest.raises(ValidationError, match="second decimal must be 0"):
        PriceEntry(product_id=1, price=value)
    with pytest.raises(ValidationError, match="second decimal must be 0"):
        OrderLineCreate(product_id=1, quantity=value)


def test_excel_price_with_second_decimal_is_refused():
    assert _parse_excel_price(5.7) == (5.7, None)
    assert _parse_excel_price("Rs. 1,250.50") == (1250.5, None)
    price, error = _parse_excel_price(5.71)
    assert price is None and "second decimal must be 0" in error
