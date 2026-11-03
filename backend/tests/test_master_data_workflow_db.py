"""
Master Data workflow, against a real Postgres database:

- Auto-generate Selling Price fills only blank prices (manual and earlier
  generated prices are kept, published prices are never touched).
- MASTER_DATA role: can see/download/publish the sheet Admin sent, and
  nothing else in Admin; branches and suppliers can't reach any of it.
- Send to Master Data makes a numbered copy; resending unchanged data
  doesn't make another one; products are never duplicated.
- Update Selling Prices publishes valid prices only, all at once, without
  touching order quantities or supplier prices; branches then see them.
"""
from datetime import date, timedelta

import pytest

from app.models.master_data_submission import MasterDataSubmission
from app.models.order import Order, OrderLine
from app.models.pricing import SupplierPrice
from app.models.product import Product
from app.services import master_data_service

DELIVERY = date.today() + timedelta(days=1)


@pytest.fixture()
def admin(make_user):
    return make_user(role="ADMIN")


@pytest.fixture()
def md_user(make_user):
    return make_user(role="MASTER_DATA")


@pytest.fixture()
def branch(make_branch):
    return make_branch()


@pytest.fixture()
def branch_user(make_user, branch):
    return make_user(role="BRANCH", branch=branch)


@pytest.fixture()
def supplier_user(make_supplier, make_user):
    return make_user(role="SUPPLIER", supplier=make_supplier())


def _quote(db, supplier_user, product, price):
    row = SupplierPrice(
        supplier_id=supplier_user.supplier_id,
        product_id=product.id,
        delivery_date=DELIVERY,
        price=price,
        unit_code="KG",
        submitted_by=supplier_user.id,
    )
    db.add(row)
    db.commit()
    return row


# --- Auto-generate ------------------------------------------------------------


def test_auto_generate_keeps_manual_prices_and_fills_blanks(client, auth_headers, admin, supplier_user, make_product, db_session):
    a = make_product(description="A")
    b = make_product(description="B")
    c = make_product(description="C")
    for p in (a, b, c):
        _quote(db_session, supplier_user, p, 100)

    # Admin types A and B by hand (through the same endpoint the sheet uses).
    for p, price in ((a, 250), (b, 400)):
        resp = client.patch(
            f"/api/v1/master-data/{p.id}", headers=auth_headers(admin), json={"field": "selling_price", "value": price}
        )
        assert resp.status_code == 200
        assert resp.json()["selling_price_source"] == "MANUAL"

    resp = client.post("/api/v1/master-data/auto-generate-selling-prices", headers=auth_headers(admin))
    assert resp.status_code == 200
    assert resp.json() == {"total_products": 3, "generated": 1, "preserved": 2, "without_price": 0}

    for p in (a, b, c):
        db_session.refresh(p)
    assert float(a.selling_price) == 250 and a.selling_price_source == "MANUAL"
    assert float(b.selling_price) == 400 and b.selling_price_source == "MANUAL"
    # Same formula as before: 100 / (1 - 0.30) = 142.86 -> 142 -> 150.
    assert float(c.selling_price) == 150 and c.selling_price_source == "AUTO"


def test_auto_generate_twice_changes_nothing_the_second_time(admin, supplier_user, make_product, db_session):
    p = make_product()
    _quote(db_session, supplier_user, p, 100)
    first = master_data_service.auto_generate_selling_prices(db_session)
    assert first.generated == 1
    # Supplier's price goes up — the earlier generated price is still kept.
    _quote(db_session, supplier_user, make_product(), 1)  # unrelated noise
    db_session.query(SupplierPrice).filter(SupplierPrice.product_id == p.id).update({"price": 500})
    db_session.commit()
    second = master_data_service.auto_generate_selling_prices(db_session)
    assert second.generated == 1  # only the new product
    db_session.refresh(p)
    assert float(p.selling_price) == 150
    assert db_session.query(Product).count() == 2  # no duplicate products


def test_auto_generate_never_touches_published_price(admin, supplier_user, make_product, db_session):
    p = make_product(published_selling_price=999)
    _quote(db_session, supplier_user, p, 100)
    master_data_service.auto_generate_selling_prices(db_session)
    db_session.refresh(p)
    assert float(p.selling_price) == 150
    assert float(p.published_selling_price) == 999


def test_auto_generate_leaves_invalid_products_blank(admin, supplier_user, make_product, db_session):
    no_cost = make_product()
    full_gp = make_product(target_gp_percent=1)
    _quote(db_session, supplier_user, full_gp, 100)
    removed = make_product(status="INACTIVE")
    _quote(db_session, supplier_user, removed, 100)

    result = master_data_service.auto_generate_selling_prices(db_session)
    assert result.generated == 0
    assert result.without_price == 2
    assert result.total_products == 2  # removed products aren't on the sheet
    for p in (no_cost, full_gp, removed):
        db_session.refresh(p)
        assert p.selling_price is None


def test_clearing_a_price_clears_its_source(client, auth_headers, admin, make_product, db_session):
    p = make_product(selling_price=300, selling_price_source="MANUAL")
    resp = client.patch(
        f"/api/v1/master-data/{p.id}", headers=auth_headers(admin), json={"field": "selling_price", "value": None}
    )
    assert resp.status_code == 200
    db_session.refresh(p)
    assert p.selling_price is None and p.selling_price_source is None


# --- Role permissions -----------------------------------------------------------


ADMIN_ONLY = [
    ("get", "/api/v1/master-data"),
    ("get", "/api/v1/master-data/export"),
    ("post", "/api/v1/master-data/auto-generate-selling-prices"),
    ("post", "/api/v1/master-data/send"),
    ("post", "/api/v1/master-data/send-email"),
    ("get", "/api/v1/users"),
    ("get", "/api/v1/branches"),
    ("get", "/api/v1/suppliers"),
    ("get", "/api/v1/orders/admin/matrix"),
    ("get", "/api/v1/settings/master-data-email"),
    ("get", "/api/v1/audit-logs"),
    ("get", "/api/v1/products/all"),
    ("post", "/api/v1/products"),
]


@pytest.mark.parametrize("method,path", ADMIN_ONLY)
def test_master_data_user_cannot_reach_admin_modules(client, auth_headers, md_user, method, path):
    resp = getattr(client, method)(path, headers=auth_headers(md_user), **({"json": {}} if method == "post" else {}))
    assert resp.status_code == 403


def test_master_data_user_cannot_edit_product_master_data(client, auth_headers, md_user, make_product):
    p = make_product()
    resp = client.patch(
        f"/api/v1/master-data/{p.id}", headers=auth_headers(md_user), json={"field": "selling_price", "value": 100}
    )
    assert resp.status_code == 403
    assert client.delete(f"/api/v1/products/{p.id}", headers=auth_headers(md_user)).status_code == 403


def test_master_data_user_cannot_touch_orders(client, auth_headers, md_user):
    assert client.get("/api/v1/orders/mine/today", headers=auth_headers(md_user)).status_code == 403
    assert client.get("/api/v1/orders", headers=auth_headers(md_user)).json() == []


@pytest.mark.parametrize(
    "method,path",
    [("get", "/api/v1/master-data/team"), ("get", "/api/v1/master-data/team/export"), ("post", "/api/v1/master-data/team/publish")],
)
def test_branch_and_supplier_cannot_reach_master_data_team(client, auth_headers, branch_user, supplier_user, method, path):
    for user in (branch_user, supplier_user):
        assert getattr(client, method)(path, headers=auth_headers(user)).status_code == 403
    assert getattr(client, method)(path).status_code == 401


def test_admin_can_view_but_not_publish(client, auth_headers, admin, make_product):
    make_product(selling_price=100, selling_price_source="MANUAL")
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    assert client.get("/api/v1/master-data/team", headers=auth_headers(admin)).status_code == 200
    assert client.post("/api/v1/master-data/team/publish", headers=auth_headers(admin)).status_code == 403


def test_login_sends_master_data_user_to_their_page(client, md_user):
    resp = client.post("/api/v1/auth/login", json={"username": md_user.username, "password": "TestPass123!"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "MASTER_DATA"
    assert resp.json()["redirect_to"] == "/master-data"


def test_admin_can_create_master_data_account(client, auth_headers, admin):
    resp = client.post(
        "/api/v1/users", headers=auth_headers(admin), json={"role": "MASTER_DATA", "username": "md.team"}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["role"] == "MASTER_DATA"
    no_name = client.post("/api/v1/users", headers=auth_headers(admin), json={"role": "MASTER_DATA"})
    assert no_name.status_code == 422


# --- Send to Master Data -----------------------------------------------------


def test_team_sees_nothing_until_admin_sends(client, auth_headers, md_user):
    assert client.get("/api/v1/master-data/team", headers=auth_headers(md_user)).status_code == 404


def test_send_then_team_sees_latest_version(client, auth_headers, admin, md_user, make_product, db_session):
    p = make_product(description="Carrot", selling_price=200, selling_price_source="MANUAL")
    first = client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    assert first.status_code == 200
    assert first.json()["version"] == 1 and first.json()["created"] is True

    # Unchanged resend: no new version.
    again = client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    assert again.json()["version"] == 1 and again.json()["created"] is False

    client.patch(f"/api/v1/master-data/{p.id}", headers=auth_headers(admin), json={"field": "selling_price", "value": 260})
    second = client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    assert second.json()["version"] == 2 and second.json()["created"] is True

    team = client.get("/api/v1/master-data/team", headers=auth_headers(md_user)).json()
    assert team["version"] == 2
    assert team["sent_by"] == admin.username
    assert [(r["description"], r["selling_price"]) for r in team["sheet"]["rows"]] == [("Carrot", 260)]
    assert db_session.query(Product).count() == 1
    assert db_session.query(MasterDataSubmission).count() == 2


def test_send_with_no_products_is_rejected(client, auth_headers, admin):
    resp = client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    assert resp.status_code == 422


def test_team_excel_has_the_sent_data(client, auth_headers, admin, md_user, make_product):
    import io

    from openpyxl import load_workbook

    make_product(product_code="P-001", description="Leeks", selling_price=340, selling_price_source="MANUAL")
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    resp = client.get("/api/v1/master-data/team/export", headers=auth_headers(md_user))
    assert resp.status_code == 200
    assert 'filename="SPAR-Master-Data-Sheet-v1-' in resp.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(resp.content)).active
    header = [c.value for c in ws[1]]
    row = dict(zip(header, [c.value for c in ws[2]]))
    assert row["Supplier Product Code"] == "P-001"
    assert row["Description"] == "Leeks"
    assert row["Selling Price"] == 340


# --- Update Selling Prices ----------------------------------------------------------


def test_publish_updates_valid_prices_only_and_keeps_orders_and_supplier_prices(
    client, auth_headers, admin, md_user, branch, branch_user, make_branch, supplier_user, make_product, db_session
):
    make_branch()  # a second branch — sees the same prices
    priced = make_product(description="Beans", selling_price=180, selling_price_source="MANUAL")
    blank = make_product(description="Okra")
    quote = _quote(db_session, supplier_user, priced, 120)
    order = Order(branch_id=branch.id, submitted_by=branch_user.id, order_date=date.today(), delivery_date=DELIVERY, status="SUBMITTED")
    db_session.add(order)
    db_session.flush()
    line = OrderLine(order_id=order.id, product_id=priced.id, quantity=12.5, unit_code="KG")
    db_session.add(line)
    db_session.commit()

    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    resp = client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["products_updated"] == 1
    assert body["branches_updated"] == 2
    assert body["skipped_missing_price"] == ["Okra"]
    assert body["skipped_invalid"] == []

    db_session.refresh(priced)
    db_session.refresh(blank)
    db_session.refresh(line)
    db_session.refresh(quote)
    assert float(priced.published_selling_price) == 180
    assert priced.selling_price_published_by == md_user.id
    assert priced.selling_price_published_at is not None
    assert blank.published_selling_price is None
    assert float(line.quantity) == 12.5
    assert float(quote.price) == 120

    # Repeat: nothing duplicated, nothing changed.
    again = client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user)).json()
    assert again["products_updated"] == 0 and again["products_unchanged"] == 1
    assert db_session.query(Product).count() == 2

    team = client.get("/api/v1/master-data/team", headers=auth_headers(md_user)).json()
    assert team["published_by"] == md_user.username
    assert team["publish_summary"]["products_unchanged"] == 1


def test_publish_skips_products_removed_after_sending(client, auth_headers, admin, md_user, make_product, db_session):
    keep = make_product(description="Kept", selling_price=100, selling_price_source="MANUAL")
    gone = make_product(description="Gone", selling_price=100, selling_price_source="MANUAL")
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    gone.status = "INACTIVE"
    db_session.commit()
    body = client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user)).json()
    assert body["products_updated"] == 1
    assert body["skipped_invalid"] == ["Gone"]
    db_session.refresh(gone)
    db_session.refresh(keep)
    assert gone.published_selling_price is None
    assert float(keep.published_selling_price) == 100


def test_publish_with_nothing_valid_changes_nothing(client, auth_headers, admin, md_user, make_product, db_session):
    p = make_product()
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    resp = client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user))
    assert resp.status_code == 422
    db_session.refresh(p)
    assert p.published_selling_price is None
    assert db_session.query(MasterDataSubmission).one().published_at is None


def test_publish_before_any_send_is_rejected(client, auth_headers, md_user):
    assert client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user)).status_code == 422




# --- Branch side: Selling Price tab -------------------------------------------------------


def _branch_prices(client, auth_headers, user, on=None):
    resp = client.get("/api/v1/selling-prices", headers=auth_headers(user), params={"on": on} if on else None)
    assert resp.status_code == 200, resp.text
    return {r["product_code"]: r["selling_price"] for r in resp.json()["rows"]}


def test_branch_sees_published_price_but_not_admins_draft(client, auth_headers, admin, md_user, branch_user, make_product):
    p = make_product(product_code="SP-9", selling_price=220, selling_price_source="MANUAL")
    make_product(product_code="SP-10")

    assert _branch_prices(client, auth_headers, branch_user) == {"SP-9": None, "SP-10": None}  # not published yet
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user))
    assert _branch_prices(client, auth_headers, branch_user) == {"SP-9": 220, "SP-10": None}

    # Admin changes the draft — branches keep seeing the published price.
    client.patch(f"/api/v1/master-data/{p.id}", headers=auth_headers(admin), json={"field": "selling_price", "value": 300})
    assert _branch_prices(client, auth_headers, branch_user)["SP-9"] == 220


def test_branch_can_look_up_prices_on_an_earlier_date(client, auth_headers, admin, md_user, branch_user, make_product, db_session):
    from app.models.selling_price_history import SellingPriceHistory

    p = make_product(product_code="SP-D", selling_price=100, selling_price_source="MANUAL")
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user))
    # Pretend that first publish happened 3 days ago.
    first = db_session.query(SellingPriceHistory).filter_by(product_id=p.id).one()
    first.published_at = first.published_at - timedelta(days=3)
    db_session.commit()

    client.patch(f"/api/v1/master-data/{p.id}", headers=auth_headers(admin), json={"field": "selling_price", "value": 150})
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))
    client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user))
    # Publishing the same version again adds no history.
    client.post("/api/v1/master-data/team/publish", headers=auth_headers(md_user))
    assert db_session.query(SellingPriceHistory).filter_by(product_id=p.id).count() == 2

    today = date.today()
    assert _branch_prices(client, auth_headers, branch_user)["SP-D"] == 150
    assert _branch_prices(client, auth_headers, branch_user, (today - timedelta(days=2)).isoformat())["SP-D"] == 100
    assert _branch_prices(client, auth_headers, branch_user, (today - timedelta(days=10)).isoformat())["SP-D"] is None


def test_suppliers_cannot_see_selling_prices(client, auth_headers, supplier_user):
    assert client.get("/api/v1/selling-prices", headers=auth_headers(supplier_user)).status_code == 403
    assert client.get("/api/v1/selling-prices").status_code == 401
    rows = client.get("/api/v1/products", headers=auth_headers(supplier_user)).json()
    assert all("selling_price" not in r for r in rows)


def test_branch_cannot_set_selling_price(client, auth_headers, branch_user, make_product):
    p = make_product()
    resp = client.patch(
        f"/api/v1/master-data/{p.id}", headers=auth_headers(branch_user), json={"field": "selling_price", "value": 1}
    )
    assert resp.status_code == 403


# --- Master Data Team: Cost Prices -----------------------------------------------------------


def test_cost_prices_grouped_by_winning_supplier_and_zipped(client, auth_headers, admin, md_user, make_supplier, make_user, make_product, db_session):
    import io
    import zipfile

    from openpyxl import load_workbook

    rkr = make_user(role="SUPPLIER", supplier=make_supplier(supplier_name="RKR"))
    chh = make_user(role="SUPPLIER", supplier=make_supplier(supplier_name="Ceylon Heredity"))
    carrot = make_product(description="Carrot", pos_code="00003662")
    leeks = make_product(description="Leeks", pos_code="00000300")
    no_pos = make_product(description="No POS", pos_code=None)
    make_product(description="Nobody quoted", pos_code="00000999")
    _quote(db_session, rkr, carrot, 4625)  # RKR highest for carrot
    _quote(db_session, chh, carrot, 4000)
    _quote(db_session, chh, leeks, 210.5)  # Ceylon Heredity only for leeks
    _quote(db_session, rkr, no_pos, 50)

    assert client.get("/api/v1/master-data/team/cost-prices", headers=auth_headers(md_user)).status_code == 404
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))

    body = client.get("/api/v1/master-data/team/cost-prices", headers=auth_headers(md_user)).json()
    groups = {s["supplier_name"]: [(i["pos_code"], i["cost_price"]) for i in s["items"]] for s in body["suppliers"]}
    assert groups == {"Ceylon Heredity": [("00000300", 210.5)], "RKR": [("00003662", 4625.0)]}
    assert body["skipped_no_pos_code"] == ["No POS"]

    resp = client.get("/api/v1/master-data/team/cost-prices/zip", headers=auth_headers(md_user))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
    assert 'filename="SPAR-Cost-Prices-v1-' in resp.headers["content-disposition"]
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    assert sorted(zf.namelist()) == ["Ceylon Heredity Cost Prices.xlsx", "RKR Cost Prices.xlsx"]

    wb = load_workbook(io.BytesIO(zf.read("RKR Cost Prices.xlsx")))
    assert wb.sheetnames == ["Transaction", "Tax"]
    ws = wb["Transaction"]
    assert [c.value for c in ws[1]][:8] == [
        "DET_LINENO", "DET_PROCODE", "DET_PRODESC", "DET_STOCKCODE", "DET_UNIT", "DET_CS", "DET_UNITQTY", "DET_CPRICE",
    ]
    assert ws.max_column == 33
    assert [c.value for c in ws[2]][:8] == [1, "00003662", None, "00003662", None, 1, 1, 4625]
    assert ws["B2"].number_format == "@"  # code kept as text, leading zeros intact
    assert all(c.value is None for c in ws[3])


@pytest.mark.parametrize("path", ["/api/v1/master-data/team/cost-prices", "/api/v1/master-data/team/cost-prices/zip"])
def test_cost_prices_hidden_from_branches_and_suppliers(client, auth_headers, branch_user, supplier_user, path):
    for user in (branch_user, supplier_user):
        assert client.get(path, headers=auth_headers(user)).status_code == 403


# --- Master Data Team: Selling Prices --------------------------------------------------------


def test_selling_prices_list_and_pos_excel(client, auth_headers, admin, md_user, make_product):
    import io

    from openpyxl import load_workbook

    make_product(description="Grapes", pos_code="00019411", selling_price=1270, selling_price_source="MANUAL")
    make_product(description="Melon", pos_code="00022986", selling_price=2140, selling_price_source="AUTO")
    make_product(description="No POS", pos_code=None, selling_price=100, selling_price_source="MANUAL")
    make_product(description="No price", pos_code="00000001")

    assert client.get("/api/v1/master-data/team/selling-prices", headers=auth_headers(md_user)).status_code == 404
    client.post("/api/v1/master-data/send", headers=auth_headers(admin))

    body = client.get("/api/v1/master-data/team/selling-prices", headers=auth_headers(md_user)).json()
    assert {(i["pos_code"], i["selling_price"]) for i in body["items"]} == {("00019411", 1270), ("00022986", 2140)}
    assert body["skipped_no_pos_code"] == ["No POS"]
    assert body["without_selling_price"] == 1

    resp = client.get("/api/v1/master-data/team/selling-prices/excel", headers=auth_headers(md_user))
    assert resp.status_code == 200
    assert 'filename="SPAR-Selling-Prices-v1-' in resp.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Transaction", "Tax"]
    ws = wb["Transaction"]
    assert ws.max_column == 32
    assert [c.value for c in ws[1]][:9] == [
        "DET_LINENO", "DET_PROCODE", "DET_PRODESC", "DET_STOCKCODE", "DET_UNIT",
        "DET_CS", "DET_UNITQTY", "DET_CPRICE", "DET_SPRICE",
    ]
    rows = [[c.value for c in r][:9] for r in ws.iter_rows(min_row=2) if r[0].value is not None]
    assert rows == [  # sheet order: category, then description
        [1, "00019411", None, "00019411", None, 1, 1, None, 1270],
        [2, "00022986", None, "00022986", None, 1, 1, None, 2140],
    ]
    assert ws["B2"].number_format == "@" and ws["I2"].number_format == "0.00"


@pytest.mark.parametrize("path", ["/api/v1/master-data/team/selling-prices", "/api/v1/master-data/team/selling-prices/excel"])
def test_selling_prices_hidden_from_branches_and_suppliers(client, auth_headers, branch_user, supplier_user, path):
    for user in (branch_user, supplier_user):
        assert client.get(path, headers=auth_headers(user)).status_code == 403
