"""
DB-backed tests for pricing_service — supplier price submission, admin
adjustment, send/unsend, and supplier isolation. Covers H-4's "Supplier
Pricing" category.
"""
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.core.errors import ValidationFailedError, PermissionDeniedError
from app.models.pricing import SupplierPrice
from app.models.system import SystemSetting
from app.schemas.pricing import PriceSubmitRequest, PriceEntry
from app.services import pricing_service


@pytest.fixture()
def admin_user(make_user):
    return make_user(role="ADMIN")


@pytest.fixture()
def open_price_window(db_session, admin_user):
    db_session.add(SystemSetting(key="supplier_price_deadline", value="23:59", updated_by=admin_user.id))
    db_session.commit()


@pytest.fixture()
def supplier_ctx(make_supplier, make_user, make_product, open_price_window):
    supplier = make_supplier()
    supplier_user = make_user(role="SUPPLIER", supplier=supplier)
    product = make_product()
    return supplier_user, product


def test_submit_price_creates_row(db_session, supplier_ctx):
    supplier_user, product = supplier_ctx
    saved = pricing_service.submit_prices(
        db_session, supplier_user, PriceSubmitRequest(prices=[PriceEntry(product_id=product.id, price=150)])
    )
    assert len(saved) == 1
    assert float(saved[0].price) == 150.0


def test_resubmit_updates_not_duplicates(db_session, supplier_ctx):
    supplier_user, product = supplier_ctx
    pricing_service.submit_prices(
        db_session, supplier_user, PriceSubmitRequest(prices=[PriceEntry(product_id=product.id, price=150)])
    )
    pricing_service.submit_prices(
        db_session, supplier_user, PriceSubmitRequest(prices=[PriceEntry(product_id=product.id, price=175)])
    )
    from app.models.pricing import SupplierPrice

    rows = (
        db_session.query(SupplierPrice)
        .filter(SupplierPrice.supplier_id == supplier_user.supplier_id, SupplierPrice.product_id == product.id)
        .all()
    )
    assert len(rows) == 1
    assert float(rows[0].price) == 175.0


def test_resubmit_clears_prices_dropped_from_new_submission(db_session, supplier_ctx, make_product):
    supplier_user, product_a = supplier_ctx
    product_b = make_product()

    pricing_service.submit_prices(
        db_session,
        supplier_user,
        PriceSubmitRequest(prices=[PriceEntry(product_id=product_a.id, price=150), PriceEntry(product_id=product_b.id, price=200)]),
    )
    pricing_service.submit_prices(
        db_session, supplier_user, PriceSubmitRequest(prices=[PriceEntry(product_id=product_b.id, price=210)])
    )

    rows = db_session.query(SupplierPrice).filter(SupplierPrice.supplier_id == supplier_user.supplier_id).all()
    assert {r.product_id: float(r.price) for r in rows} == {product_b.id: 210.0}


def test_missing_price_rejected_at_schema_level():
    with pytest.raises(ValidationError):
        PriceSubmitRequest(prices=[])


def test_invalid_negative_price_rejected_at_schema_level():
    with pytest.raises(ValidationError):
        PriceEntry(product_id=1, price=-10)


def test_oversized_price_rejected_at_schema_level():
    with pytest.raises(ValidationError):
        PriceEntry(product_id=1, price=999999999)


def test_duplicate_product_in_same_submission_rejected(db_session, supplier_ctx):
    supplier_user, product = supplier_ctx
    with pytest.raises(ValidationFailedError):
        pricing_service.submit_prices(
            db_session,
            supplier_user,
            PriceSubmitRequest(
                prices=[
                    PriceEntry(product_id=product.id, price=100),
                    PriceEntry(product_id=product.id, price=200),
                ]
            ),
        )


def test_unknown_product_rejected(db_session, supplier_ctx):
    supplier_user, _product = supplier_ctx
    with pytest.raises(ValidationFailedError):
        pricing_service.submit_prices(
            db_session, supplier_user, PriceSubmitRequest(prices=[PriceEntry(product_id=999999, price=100)])
        )


def test_non_supplier_account_cannot_submit_prices(db_session, make_user, make_branch, make_product, open_price_window):
    branch = make_branch()
    branch_user = make_user(role="BRANCH", branch=branch)
    product = make_product()
    with pytest.raises(PermissionDeniedError):
        pricing_service.submit_prices(
            db_session, branch_user, PriceSubmitRequest(prices=[PriceEntry(product_id=product.id, price=100)])
        )


def test_supplier_isolation_one_supplier_cannot_see_another(db_session, make_supplier, make_user, make_product, open_price_window):
    product = make_product()
    supplier_a = make_supplier()
    user_a = make_user(role="SUPPLIER", supplier=supplier_a)
    supplier_b = make_supplier()
    user_b = make_user(role="SUPPLIER", supplier=supplier_b)

    pricing_service.submit_prices(
        db_session, user_a, PriceSubmitRequest(prices=[PriceEntry(product_id=product.id, price=100)])
    )
    pricing_service.submit_prices(
        db_session, user_b, PriceSubmitRequest(prices=[PriceEntry(product_id=product.id, price=200)])
    )

    a_prices = pricing_service.list_my_prices(db_session, user_a)
    b_prices = pricing_service.list_my_prices(db_session, user_b)
    assert len(a_prices) == 1 and float(a_prices[0].price) == 100.0
    assert len(b_prices) == 1 and float(b_prices[0].price) == 200.0


def test_admin_adjust_send_unsend_price_flow(db_session, supplier_ctx, admin_user):
    supplier_user, product = supplier_ctx
    saved = pricing_service.submit_prices(
        db_session, supplier_user, PriceSubmitRequest(prices=[PriceEntry(product_id=product.id, price=100)])
    )
    price_id = saved[0].id

    adjusted = pricing_service.set_adjusted_price(db_session, admin_user, price_id, 90)
    assert float(adjusted.adjusted_price) == 90.0
    assert adjusted.sent_to_supplier_at is None  # draft-only until explicitly sent

    sent = pricing_service.send_adjusted_price(db_session, admin_user, price_id)
    assert sent.sent_to_supplier_at is not None

    unsent = pricing_service.unsend_adjusted_price(db_session, admin_user, price_id)
    assert unsent.sent_to_supplier_at is None


# ---- Latest-previous-price fallback (Submit Prices auto-fill on a new
# delivery date) — get_last_prices/list_my_prices are the two reads the
# frontend combines to decide what to pre-fill; submit_prices always
# targets "today + 2" via get_price_window, so rows for other dates are
# inserted directly here to simulate prior days' submissions. ----


def _add_price(db_session, supplier_user, product, delivery_date, price):
    row = SupplierPrice(
        supplier_id=supplier_user.supplier_id,
        product_id=product.id,
        delivery_date=delivery_date,
        price=price,
        unit_code="KG",
        submitted_by=supplier_user.id,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_last_price_falls_back_to_yesterday_when_current_date_has_none(db_session, supplier_ctx):
    supplier_user, product = supplier_ctx
    today = date(2026, 6, 20)
    yesterday = today - timedelta(days=1)
    _add_price(db_session, supplier_user, product, yesterday, 320)

    assert pricing_service.list_my_prices(db_session, supplier_user, today) == []
    last = pricing_service.get_last_prices(db_session, supplier_user)
    assert len(last) == 1
    assert float(last[0].price) == 320.0
    assert last[0].delivery_date == yesterday


def test_last_price_skips_gaps_to_most_recent_older_submission(db_session, supplier_ctx):
    supplier_user, product = supplier_ctx
    older = date(2026, 6, 10)
    newer = date(2026, 6, 18)
    _add_price(db_session, supplier_user, product, older, 200)
    _add_price(db_session, supplier_user, product, newer, 260)

    last = pricing_service.get_last_prices(db_session, supplier_user)
    assert len(last) == 1
    assert float(last[0].price) == 260.0
    assert last[0].delivery_date == newer


def test_current_date_submission_takes_priority_over_last_price(db_session, supplier_ctx):
    supplier_user, product = supplier_ctx
    previous = date(2026, 6, 18)
    current = date(2026, 6, 20)
    _add_price(db_session, supplier_user, product, previous, 200)
    _add_price(db_session, supplier_user, product, current, 999)

    mine_current = pricing_service.list_my_prices(db_session, supplier_user, current)
    assert len(mine_current) == 1
    assert float(mine_current[0].price) == 999.0


def test_no_prior_submission_gives_no_fallback(db_session, supplier_ctx):
    supplier_user, _product = supplier_ctx
    assert pricing_service.get_last_prices(db_session, supplier_user) == []


def test_last_price_fallback_respects_supplier_isolation(
    db_session, make_supplier, make_user, make_product, open_price_window
):
    product = make_product()
    supplier_a = make_supplier()
    user_a = make_user(role="SUPPLIER", supplier=supplier_a)
    supplier_b = make_supplier()
    user_b = make_user(role="SUPPLIER", supplier=supplier_b)

    _add_price(db_session, user_a, product, date(2026, 6, 10), 111)
    _add_price(db_session, user_b, product, date(2026, 6, 10), 222)

    last_a = pricing_service.get_last_prices(db_session, user_a)
    last_b = pricing_service.get_last_prices(db_session, user_b)
    assert len(last_a) == 1 and float(last_a[0].price) == 111.0
    assert len(last_b) == 1 and float(last_b[0].price) == 222.0
