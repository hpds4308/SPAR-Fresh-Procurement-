"""
get_stock_in_hand_all_branches: the New Order form's per-branch stock rows.
The POS call itself is stubbed — these check that each branch gets exactly
the figures the existing single-location lookup returns for its own
location code, mapped to the right product, in branch-name order.
"""
import pytest

from app.core.errors import PermissionDeniedError
from app.services import order_service, pos_stock_service


@pytest.fixture()
def fake_pos(monkeypatch):
    calls = []
    # {location_code: {pos_code: qty}} — what the POS "has" per location.
    data = {
        "LOC-A": {"POS1": 19.636, "POS2": 9.326},
        "LOC-B": {"POS1": 12.5},
    }

    def _fake(pos_codes, location_code):
        calls.append(location_code)
        return {c: q for c, q in data.get(location_code, {}).items() if c in pos_codes}

    monkeypatch.setattr(pos_stock_service, "get_stock_in_hand", _fake)
    return calls


def test_all_branches_stock_maps_each_branch_to_its_own_location(
    db_session, make_branch, make_user, make_product, fake_pos
):
    b_zeta = make_branch(branch_name="Zeta Stock", pos_location_code="LOC-A")
    b_alpha = make_branch(branch_name="Alpha Stock", pos_location_code="LOC-B")
    b_nocode = make_branch(branch_name="Mid Stock")  # no POS location code yet
    make_branch(branch_name="Inactive Stock", pos_location_code="LOC-A", status="INACTIVE")
    p1 = make_product(pos_code="POS1")
    p2 = make_product(pos_code="POS2")
    user = make_user(role="BRANCH", branch=b_zeta)

    result = order_service.get_stock_in_hand_all_branches(db_session, user)
    ours = [r for r in result if r["branch_id"] in {b_zeta.id, b_alpha.id, b_nocode.id}]

    assert [r["branch_name"] for r in ours] == ["Alpha Stock", "Mid Stock", "Zeta Stock"]
    assert "Inactive Stock" not in [r["branch_name"] for r in result]
    by_name = {r["branch_name"]: r for r in ours}
    assert by_name["Zeta Stock"]["stock"] == {p1.id: 19.636, p2.id: 9.326}
    assert by_name["Alpha Stock"]["stock"] == {p1.id: 12.5}
    assert by_name["Mid Stock"]["stock"] == {}
    assert [r["is_current"] for r in ours] == [False, False, True]
    # No POS call for a branch without a location code.
    assert fake_pos.count("LOC-A") == 1 and fake_pos.count("LOC-B") == 1


def test_all_branches_stock_matches_single_branch_lookup(
    db_session, make_branch, make_user, make_product, fake_pos
):
    branch = make_branch(branch_name="Same Stock", pos_location_code="LOC-A")
    make_product(pos_code="POS1")
    make_product(pos_code="POS2")
    user = make_user(role="BRANCH", branch=branch)

    single = order_service.get_stock_in_hand_for_branch(db_session, user)
    everyone = order_service.get_stock_in_hand_all_branches(db_session, user)
    mine = next(r for r in everyone if r["branch_id"] == branch.id)
    assert mine["stock"] == single


def test_all_branches_stock_requires_branch_account(db_session, make_user, fake_pos):
    with pytest.raises(PermissionDeniedError):
        order_service.get_stock_in_hand_all_branches(db_session, make_user(role="ADMIN"))
