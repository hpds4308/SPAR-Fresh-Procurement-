"""
BUG-001 (QA): every request field backed by a NUMERIC(10,2) database
column previously validated only a lower bound (> 0 or >= 0), so a value
at or above the column's own precision limit sailed past Pydantic and
crashed with an unhandled 500 once it reached the database. These tests
pin the fix (see app/schemas/_limits.py) directly at the schema layer —
no live server or database needed, matching the rest of this suite.
"""
import pytest
from pydantic import ValidationError

from app.schemas._limits import MAX_NUMERIC_10_2
from app.schemas.assignment import AssignmentIn
from app.schemas.master_data import MasterDataFieldUpdateRequest
from app.schemas.order import DeliveryLineConfirm, OrderLineCreate
from app.schemas.pricing import AdjustPriceRequest, PriceEntry, ReferencePriceSetRequest
from app.schemas.supplier_order import SupplierOrderItemIn


@pytest.mark.parametrize("value", [1, 10, 100, 1000, MAX_NUMERIC_10_2])
def test_order_line_quantity_accepts_valid_and_boundary_values(value):
    OrderLineCreate(product_id=1, quantity=value)


@pytest.mark.parametrize("value", [-1, 0, MAX_NUMERIC_10_2 + 1, 999999999])
def test_order_line_quantity_rejects_invalid_and_oversized_values(value):
    with pytest.raises(ValidationError):
        OrderLineCreate(product_id=1, quantity=value)


def test_order_line_quantity_rejects_null_and_non_numeric_string():
    with pytest.raises(ValidationError):
        OrderLineCreate(product_id=1, quantity=None)
    with pytest.raises(ValidationError):
        OrderLineCreate(product_id=1, quantity="not-a-number")


def test_delivery_received_quantity_respects_the_same_ceiling():
    DeliveryLineConfirm(product_id=1, received_quantity=MAX_NUMERIC_10_2)
    with pytest.raises(ValidationError):
        DeliveryLineConfirm(product_id=1, received_quantity=MAX_NUMERIC_10_2 + 1)


@pytest.mark.parametrize("value", [1, 100, MAX_NUMERIC_10_2])
def test_supplier_price_accepts_valid_and_boundary_values(value):
    PriceEntry(product_id=1, price=value)


@pytest.mark.parametrize("value", [-1, 0, MAX_NUMERIC_10_2 + 1])
def test_supplier_price_rejects_invalid_and_oversized_values(value):
    with pytest.raises(ValidationError):
        PriceEntry(product_id=1, price=value)


def test_assignment_quantity_and_price_both_respect_the_ceiling():
    AssignmentIn(supplier_id=1, quantity=MAX_NUMERIC_10_2, agreed_price=MAX_NUMERIC_10_2)
    with pytest.raises(ValidationError):
        AssignmentIn(supplier_id=1, quantity=MAX_NUMERIC_10_2 + 1, agreed_price=10)
    with pytest.raises(ValidationError):
        AssignmentIn(supplier_id=1, quantity=10, agreed_price=MAX_NUMERIC_10_2 + 1)


def test_supplier_order_item_quantity_and_price_both_respect_the_ceiling():
    SupplierOrderItemIn(branch_id=1, product_id=1, quantity=MAX_NUMERIC_10_2, agreed_price=MAX_NUMERIC_10_2)
    with pytest.raises(ValidationError):
        SupplierOrderItemIn(branch_id=1, product_id=1, quantity=MAX_NUMERIC_10_2 + 1)
    with pytest.raises(ValidationError):
        SupplierOrderItemIn(branch_id=1, product_id=1, quantity=10, agreed_price=MAX_NUMERIC_10_2 + 1)


def test_reference_price_custom_validator_rejects_oversized_value():
    ReferencePriceSetRequest(price=MAX_NUMERIC_10_2)
    with pytest.raises(ValidationError):
        ReferencePriceSetRequest(price=MAX_NUMERIC_10_2 + 1)
    # Null is the documented "clear this field" signal, not an error.
    assert ReferencePriceSetRequest(price=None).price is None


def test_adjusted_price_custom_validator_rejects_oversized_value():
    AdjustPriceRequest(adjusted_price=MAX_NUMERIC_10_2)
    with pytest.raises(ValidationError):
        AdjustPriceRequest(adjusted_price=MAX_NUMERIC_10_2 + 1)


def test_master_data_selling_price_rejects_oversized_value():
    # Selling price rounds up to the next 10, so the largest storable value
    # is the last multiple of 10 under the column ceiling.
    MasterDataFieldUpdateRequest(field="selling_price", value=99_999_990)
    with pytest.raises(ValidationError):
        MasterDataFieldUpdateRequest(field="selling_price", value=MAX_NUMERIC_10_2)


def test_master_data_selling_price_rounds_up_to_next_10():
    assert MasterDataFieldUpdateRequest(field="selling_price", value=1342).value == 1350
    assert MasterDataFieldUpdateRequest(field="selling_price", value=1350).value == 1350
    # Decimals are dropped before rounding up.
    assert MasterDataFieldUpdateRequest(field="selling_price", value=1340.99).value == 1340
    assert MasterDataFieldUpdateRequest(field="selling_price", value=787.67).value == 790
    for raw, expected in [(456, 460), (201, 210), (405, 410), (672, 680), (0.5, 10)]:
        assert MasterDataFieldUpdateRequest(field="selling_price", value=raw).value == expected


def test_master_data_target_gp_percent_was_already_safely_bounded():
    # Numeric(5,4) with an existing 0-1 business check — not part of this
    # fix, confirmed here so a future change to the ceiling above doesn't
    # accidentally loosen this already-correct, separately-bounded field.
    MasterDataFieldUpdateRequest(field="target_gp_percent", value=0.30)
    with pytest.raises(ValidationError):
        MasterDataFieldUpdateRequest(field="target_gp_percent", value=1.5)
