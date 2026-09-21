"""
QA: order/assignment business rules, Excel upload, input validation.

Evidence for BUG-06 (Excel 'nan'), BUG-08 (rounding to 0.00 slips past gt=0),
BUG-09 (NUL bytes -> 500), BUG-10 (unbounded free-text), BUG-11 (server-local
date.today()), BUG-12 (admin line edits do not recompute order status).
"""
import io
from datetime import date, timedelta

import openpyxl
import pytest
from pydantic import ValidationError

from app.schemas.assignment import AssignmentIn
from app.schemas.order import OrderLineCreate
from app.schemas.pricing import PriceEntry


# ---------------------------------------------------------------- helpers
def _xlsx(rows, headers=("Product Code", "POS Code", "Product Description", "Unit", "Quantity")):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload(client, headers, content):
    return client.post("/api/v1/orders/draft/preview-excel", headers=headers,
                       files={"file": ("o.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})


# ------------------------------------------------------------ Excel upload
_BUG06 = pytest.mark.xfail(strict=True, reason="BUG-06: a text cell 'nan' passes float() and both range checks in "
                           "order_service._parse_excel_quantity (order_service.py:214-225), then the NaN cannot be JSON-encoded -> HTTP 500")


@pytest.mark.parametrize("bad", [
    pytest.param("nan", marks=_BUG06), pytest.param("NaN", marks=_BUG06),
    "inf", "-inf", "1e999", "5,5", "５",
])
def test_excel_non_finite_or_odd_quantities_never_become_valid_lines(client_no_raise, auth_headers, make_user, make_branch, make_product, bad):
    """BUG-06 probe: a text cell such as 'nan' passes float() and both range checks in
    order_service._parse_excel_quantity (nan comparisons are always False)."""
    user = make_user(role="BRANCH", branch=make_branch())
    p = make_product()
    r = _upload(client_no_raise, auth_headers(user), _xlsx([[p.product_code, "", p.description, "kg", bad]]))
    if r.status_code != 200:
        pytest.fail(f"HTTP {r.status_code} for quantity cell {bad!r} (BUG-06: expected a clean per-row error)")
    row = r.json()["lines"][0]
    is_valid_looking = row["error"] is None
    if bad == "５":  # full-width digit: float('５') == 5.0 -> accepted; harmless, documents behaviour
        return
    assert not is_valid_looking, f"{bad!r} was accepted as a valid quantity: {row}"


def test_excel_wrong_filetype_is_a_clean_422(client, auth_headers, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch())
    r = client.post("/api/v1/orders/draft/preview-excel", headers=auth_headers(user),
                    files={"file": ("o.xlsx", b"this is not a zip", "application/octet-stream")})
    assert r.status_code == 422


def test_excel_over_5mb_is_rejected(client, auth_headers, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch())
    r = client.post("/api/v1/orders/draft/preview-excel", headers=auth_headers(user),
                    files={"file": ("o.xlsx", b"0" * (5 * 1024 * 1024 + 1), "application/octet-stream")})
    assert r.status_code == 422


def test_excel_formula_and_script_text_in_description_is_not_echoed_from_file(client, auth_headers, make_user, make_branch, make_product):
    """Description shown in the preview comes from the DB product, never from the uploaded cell."""
    user = make_user(role="BRANCH", branch=make_branch())
    p = make_product(description="Real Tomato")
    r = _upload(client, auth_headers(user), _xlsx([[p.product_code, "", "=HYPERLINK(\"http://evil\")<script>alert(1)</script>", "kg", 2]]))
    assert r.status_code == 200
    assert r.json()["lines"][0]["description"] == "Real Tomato"


def _row_flood_xlsx(rows: int) -> bytes:
    """A small-on-the-wire .xlsx that expands to `rows` non-empty rows (deflate squeezes repeated XML ~400:1)."""
    import zipfile

    sheet = ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             '<row><c t="inlineStr"><is><t>Product Code</t></is></c><c t="inlineStr"><is><t>Quantity</t></is></c></row>'
             + "<row><c><v>1</v></c></row>" * rows + "</sheetData></worksheet>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def test_sec02_excel_row_flood_is_rejected(client, auth_headers, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch())
    data = _row_flood_xlsx(60_000)
    assert len(data) < 5 * 1024 * 1024  # passes the existing 5 MB upload check
    r = _upload(client, auth_headers(user), data)
    assert r.status_code == 422
    assert "too large or has too many rows" in r.json()["detail"]


# ------------------------------------------------- rounding vs. gt=0 (schemas)
@pytest.mark.xfail(strict=True, reason="BUG-08: Field(gt=0) is checked BEFORE the round_price validator, so 0.004 -> 0.00 is accepted "
                   "(schemas/pricing.py:7-15) - a supplier can submit a free price")
def test_bug08_price_that_rounds_to_zero_is_rejected():
    with pytest.raises(ValidationError):
        PriceEntry(product_id=1, price=0.004)


@pytest.mark.xfail(strict=True, reason="BUG-08: same pattern in schemas/order.py:7-16 - a 0.00 quantity line is stored")
def test_bug08_order_quantity_that_rounds_to_zero_is_rejected():
    with pytest.raises(ValidationError):
        OrderLineCreate(product_id=1, quantity=0.004)


@pytest.mark.xfail(strict=True, reason="BUG-08: same pattern in schemas/assignment.py:48-57 - agreed_price 0.00 / quantity 0.00 accepted")
def test_bug08_assignment_that_rounds_to_zero_is_rejected():
    with pytest.raises(ValidationError):
        AssignmentIn(supplier_id=1, quantity=10, agreed_price=0.004)


def test_price_boundaries_that_should_work():
    assert PriceEntry(product_id=1, price=0.01).price == 0.01
    assert PriceEntry(product_id=1, price=99999999.99).price == 99999999.99
    for bad in (0, -1, 100000000.0, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            PriceEntry(product_id=1, price=bad)


# ------------------------------------------------- hostile / unusual text input
@pytest.mark.xfail(strict=True, reason="BUG-09: a NUL (\\x00) byte reaches psycopg2 which raises ValueError -> HTTP 500 "
                   "(no validation on MessageCreate.body, schemas/message.py:17)")
def test_bug09_nul_byte_in_chat_message_is_a_clean_4xx(client_no_raise, auth_headers, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch())
    r = client_no_raise.post("/api/v1/messages/mine", headers=auth_headers(user), json={"body": "hello\u0000world"})
    assert 400 <= r.status_code < 500


@pytest.mark.xfail(strict=True, reason="BUG-09: NUL byte in the login username also 500s instead of 401 (auth_service.py:33)")
def test_bug09_nul_byte_in_login_username_is_401(client_no_raise):
    r = client_no_raise.post("/api/v1/auth/login", json={"username": "a\u0000b", "password": "x"})
    assert r.status_code == 401


@pytest.mark.parametrize("body", [
    "' OR 1=1 --", "\"; DROP TABLE users; --", "<script>alert(1)</script>", "${jndi:ldap://x}", "{{7*7}}",
    "සුභ දවසක්! வணக்கம்", "😀🥕🍅 emoji", "line1\nline2\ttab", "a" * 2000,
])
def test_chat_message_accepts_unicode_and_stores_hostile_strings_verbatim(client, auth_headers, make_user, make_branch, body):
    """Stored as data and returned verbatim; the React UI renders as text (no dangerouslySetInnerHTML anywhere in src/)."""
    user = make_user(role="BRANCH", branch=make_branch())
    r = client.post("/api/v1/messages/mine", headers=auth_headers(user), json={"body": body})
    assert r.status_code == 200 and r.json()["body"] == body


def test_chat_message_length_and_empty_limits(client, auth_headers, make_user, make_branch):
    user = make_user(role="BRANCH", branch=make_branch())
    h = auth_headers(user)
    assert client.post("/api/v1/messages/mine", headers=h, json={"body": ""}).status_code == 422
    assert client.post("/api/v1/messages/mine", headers=h, json={"body": "a" * 2001}).status_code == 422


@pytest.mark.parametrize("username", ["' OR '1'='1", "admin'--", "admin\" OR \"\"=\"", "%", "🥕"])
def test_login_sql_injection_style_usernames_are_plain_401(client, username):
    assert client.post("/api/v1/auth/login", json={"username": username, "password": "x"}).status_code == 401


@pytest.mark.xfail(strict=True, reason="BUG-10: OrderCreate.notes / OrderLineCreate.notes / DeliveryLineConfirm.notes have no max_length; "
                   "a 3 MB note is stored (schemas/order.py:10,20,117) and there is no request-size limit anywhere")
def test_bug10_giant_order_note_is_rejected(client, auth_headers, make_user, make_branch, make_product, open_order_window):
    user = make_user(role="BRANCH", branch=make_branch())
    open_order_window(user.id)
    p = make_product()
    r = client.post("/api/v1/orders/draft", headers=auth_headers(user),
                    json={"lines": [{"product_id": p.id, "quantity": 1}], "notes": "x" * 3_000_000})
    assert r.status_code == 422


# --------------------------------------------------------- order lifecycle
def _order_with_assigned_supplier(db_session, make_user, make_branch, make_product, make_supplier):
    from app.models.order import Order, OrderLine
    from app.schemas.assignment import SetAssignmentsRequest
    from app.services import assignment_service

    admin = make_user(role="ADMIN")
    branch = make_branch()
    b_user = make_user(role="BRANCH", branch=branch)
    supplier = make_supplier()
    product = make_product()
    delivery = date.today() + timedelta(days=2)
    order = Order(branch_id=branch.id, submitted_by=b_user.id, order_date=delivery - timedelta(days=2),
                  delivery_date=delivery, status="SUBMITTED")
    db_session.add(order)
    db_session.flush()
    db_session.add(OrderLine(order_id=order.id, product_id=product.id, quantity=10, unit_code="KG"))
    db_session.commit()
    assignment_service.set_assignments(
        db_session, admin, product.id, delivery,
        SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=supplier.id, quantity=10, agreed_price=5)]))
    db_session.refresh(order)
    assert order.status == "ASSIGNED", "precondition: full assignment must flip the order to ASSIGNED"
    return admin, branch, product, order, delivery


@pytest.mark.xfail(strict=True, reason="BUG-12: admin_add_order_line never calls _recompute_order_statuses_for_date "
                   "(only caller is assignment_service.py:195), so raising demand from 10 to 25 leaves the order ASSIGNED "
                   "although only 10 is covered - contradicts assignment_service.py module docstring")
def test_bug12_raising_demand_on_assigned_order_reverts_status(db_session, make_user, make_branch, make_product, make_supplier):
    from app.services import order_service

    admin, branch, product, order, delivery = _order_with_assigned_supplier(
        db_session, make_user, make_branch, make_product, make_supplier)
    order_service.admin_add_order_line(db_session, admin, branch.id, product.id, delivery, 25)
    db_session.refresh(order)
    assert order.status == "SUBMITTED"


@pytest.mark.xfail(strict=False, reason="RISK-04: Admin can still add lines to a CONFIRMED order (branch already signed off the "
                   "delivery), silently changing a closed record. Needs a product decision - see QA_REPORT")
def test_risk04_admin_cannot_edit_confirmed_order(db_session, make_user, make_branch, make_product, make_supplier):
    from app.core.errors import AppError
    from app.services import order_service

    admin, branch, product, order, delivery = _order_with_assigned_supplier(
        db_session, make_user, make_branch, make_product, make_supplier)
    order.status = "CONFIRMED"
    db_session.commit()
    with pytest.raises(AppError):
        order_service.admin_add_order_line(db_session, admin, branch.id, product.id, delivery, 99)


def test_over_assignment_is_rejected(db_session, make_user, make_branch, make_product, make_supplier):
    from app.core.errors import ValidationFailedError
    from app.schemas.assignment import SetAssignmentsRequest
    from app.services import assignment_service

    admin, branch, product, order, delivery = _order_with_assigned_supplier(
        db_session, make_user, make_branch, make_product, make_supplier)
    s2 = make_supplier()
    with pytest.raises(ValidationFailedError):
        assignment_service.set_assignments(
            db_session, admin, product.id, delivery,
            SetAssignmentsRequest(assignments=[AssignmentIn(supplier_id=s2.id, quantity=10.5, agreed_price=5)]))


def test_branch_cannot_confirm_delivery_of_unassigned_order(client, auth_headers, make_user, make_branch, make_product, db_session):
    from app.models.order import Order, OrderLine

    branch = make_branch()
    user = make_user(role="BRANCH", branch=branch)
    p = make_product()
    o = Order(branch_id=branch.id, submitted_by=user.id, order_date=date.today(),
              delivery_date=date.today() + timedelta(days=2), status="SUBMITTED")
    db_session.add(o)
    db_session.flush()
    db_session.add(OrderLine(order_id=o.id, product_id=p.id, quantity=3, unit_code="KG"))
    db_session.commit()
    r = client.put(f"/api/v1/orders/{o.id}/confirm-delivery", headers=auth_headers(user),
                   json={"lines": [{"product_id": p.id, "received_quantity": 3}]})
    assert r.status_code == 422


def test_second_branch_submit_same_day_is_rejected(client, auth_headers, make_user, make_branch, make_product, open_order_window):
    user = make_user(role="BRANCH", branch=make_branch())
    open_order_window(user.id)
    p = make_product()
    payload = {"lines": [{"product_id": p.id, "quantity": 2}]}
    assert client.post("/api/v1/orders", headers=auth_headers(user), json=payload).status_code == 200
    assert client.post("/api/v1/orders", headers=auth_headers(user), json=payload).status_code == 422


@pytest.mark.xfail(strict=False, reason="BUG-11: reports.py:38/58 and master_data.py:80 use server-local date.today() while all order/price "
                   "logic uses Asia/Colombo; on a UTC host the default report window is off by one day for 5.5h each night")
def test_bug11_report_default_range_uses_business_timezone(monkeypatch, client, auth_headers, make_user):
    import app.api.v1.reports as reports_mod
    from datetime import datetime
    from zoneinfo import ZoneInfo

    class FakeDate(date):
        @classmethod
        def today(cls):  # what a UTC server sees at 01:00 Colombo time on 2026-06-16
            return date(2026, 6, 15)

    monkeypatch.setattr(reports_mod, "date", FakeDate)
    admin = make_user(role="ADMIN")
    r = client.get("/api/v1/reports/admin/summary", headers=auth_headers(admin))
    assert r.status_code == 200
    colombo_today = datetime(2026, 6, 15, 19, 30, tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("Asia/Colombo")).date()
    assert r.json()["end_date"] == colombo_today.isoformat()
