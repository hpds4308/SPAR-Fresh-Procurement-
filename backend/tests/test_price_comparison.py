"""
QA gap: second-lowest supplier price, and the savings figure derived from
it. Pins the exact scenarios the QA report specified, including the
ambiguous one (a tie at the lowest price) — see
pricing_service.second_lowest_price for the tie-breaking rule this picks
and why it's a real interpretation choice, not an obvious one, and
assignment_service.compute_savings for the formula itself (adopted
directly from the spec's own worked example, not independently derived).
"""
from app.services.assignment_service import compute_savings
from app.services.pricing_service import second_lowest_price


def test_two_suppliers():
    assert second_lowest_price([300, 280]) == 300


def test_three_suppliers():
    assert second_lowest_price([300, 280, 320]) == 300


def test_tie_at_the_lowest_price_skips_to_the_next_distinct_tier():
    # 300/300/320 — the lowest is 300 (shared by two suppliers); the
    # second-lowest is the next genuinely different price, 320, not
    # another 300.
    assert second_lowest_price([300, 300, 320]) == 320


def test_all_suppliers_tied_has_no_second_tier():
    assert second_lowest_price([300, 300, 300]) is None


def test_only_one_supplier_has_no_second_lowest():
    assert second_lowest_price([300]) is None


def test_no_supplier_prices_at_all():
    assert second_lowest_price([]) is None


def test_decimal_prices():
    assert second_lowest_price([19.99, 20.50, 19.99]) == 20.50


# ---- Savings: (second_lowest - agreed_price) x quantity ----


def test_savings_when_the_cheapest_supplier_was_selected():
    # Spec's own worked example: quotes 300/280/320, second-lowest is
    # 300; selecting the cheapest (280) at qty 10 saves (300-280)*10=200
    # versus the runner-up.
    assert compute_savings(second_lowest=300, agreed_price=280, quantity=10) == 200


def test_savings_is_negative_when_a_pricier_supplier_was_selected():
    # Selecting the MOST expensive of the three (320) costs more than the
    # runner-up would have — a real, useful signal, not clamped to zero.
    assert compute_savings(second_lowest=300, agreed_price=320, quantity=10) == -200


def test_savings_is_zero_when_agreed_price_equals_second_lowest():
    assert compute_savings(second_lowest=300, agreed_price=300, quantity=10) == 0


def test_savings_is_none_with_no_second_lowest_to_compare_against():
    # Only one supplier ever quoted, or none at all — second_lowest_price
    # itself already returns None for both; savings must follow suit
    # rather than inventing a comparison that doesn't exist.
    assert compute_savings(second_lowest=None, agreed_price=280, quantity=10) is None


def test_savings_with_decimal_price_and_large_quantity():
    assert compute_savings(second_lowest=19.99, agreed_price=15.50, quantity=1000) == 4490.0
