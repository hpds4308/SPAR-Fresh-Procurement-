"""
Imported Fruit items are ordered in whole cases: a branch may order 1, 2
or 3 cases, never 1.5. Other items keep their one-decimal quantities.
"""
import pytest

from app.core.errors import ValidationFailedError
from app.models.product import ProductUnit
from app.schemas.order import OrderCreate
from app.services import order_service


@pytest.fixture
def case_product(db_session, make_product):
    unit = db_session.query(ProductUnit).filter(ProductUnit.code == "case").one()
    return make_product(unit_id=unit.id, case_kg=12)


def _order(product_id, quantity):
    return OrderCreate(lines=[{"product_id": product_id, "quantity": quantity}])


def test_whole_cases_are_accepted(db_session, case_product):
    order_service._validate_lines(db_session, _order(case_product.id, 3))


@pytest.mark.parametrize("quantity", [1.2, 1.5, 2.7])
def test_part_cases_are_refused(db_session, case_product, quantity):
    with pytest.raises(ValidationFailedError, match="whole cases"):
        order_service._validate_lines(db_session, _order(case_product.id, quantity))


def test_kg_items_keep_decimals(db_session, make_product):
    order_service._validate_lines(db_session, _order(make_product().id, 1.5))
