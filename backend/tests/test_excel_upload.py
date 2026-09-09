"""
DB-backed tests for the order Excel upload/preview endpoint (M-7).

Replaces an earlier ad-hoc script (backend/test_excel_upload.py, deleted —
it was a live-server-only script using urllib, left outside tests/ by
mistake, and broke pytest collection entirely since it made a real HTTP
call at import time). Same 12 scenarios, now real, isolated, CI-repeatable
pytest tests against the DB-backed fixtures, hitting the real endpoint
through the `client` TestClient fixture end to end.
"""
import io

import openpyxl
import pytest

from app.models.system import SystemSetting

DEFAULT_HEADERS = ("Product Code", "POS Code", "Product Description", "Unit", "Quantity")


def _xlsx_bytes(rows, headers=DEFAULT_HEADERS):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(headers))
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def branch_user(make_branch, make_user):
    return make_user(role="BRANCH", branch=make_branch())


@pytest.fixture()
def supplier_user(make_supplier, make_user):
    return make_user(role="SUPPLIER", supplier=make_supplier())


def _upload(client, headers, content, filename="order.xlsx"):
    return client.post(
        "/api/v1/orders/draft/preview-excel",
        headers=headers,
        files={"file": (filename, content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )


def test_valid_file_real_product_codes_parses_cleanly(client, auth_headers, branch_user, make_product):
    p1, p2 = make_product(), make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg", 10], [p2.product_code, "", p2.description, "kg", 5.5]])
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid_line_count"] == 2
    assert body["error_count"] == 0


def test_missing_required_column_rejected(client, auth_headers, branch_user, make_product):
    p1 = make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg"]], headers=("Product Code", "POS Code", "Product Description", "Unit"))
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 422


def test_extra_unexpected_column_ignored_row_still_parses(client, auth_headers, branch_user, make_product):
    p1 = make_product()
    data = _xlsx_bytes(
        [[p1.product_code, "", p1.description, "kg", 10, "extra junk"]],
        headers=("Product Code", "POS Code", "Product Description", "Unit", "Quantity", "Some Random Column"),
    )
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    assert resp.json()["valid_line_count"] == 1


def test_unknown_product_code_flagged_not_crashed(client, auth_headers, branch_user):
    data = _xlsx_bytes([["9999999999", "", "FAKE PRODUCT", "kg", 10]])
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    assert resp.json()["error_count"] == 1


def test_duplicate_product_code_flagged(client, auth_headers, branch_user, make_product):
    p1 = make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg", 10], [p1.product_code, "", p1.description, "kg", 5]])
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    assert resp.json()["error_count"] == 1


def test_negative_zero_empty_text_quantity_all_flagged(client, auth_headers, branch_user, make_product):
    p1, p2, p3, p4 = make_product(), make_product(), make_product(), make_product()
    data = _xlsx_bytes(
        [
            [p1.product_code, "", p1.description, "kg", -5],
            [p2.product_code, "", p2.description, "kg", 0],
            [p3.product_code, "", p3.description, "kg", None],
            [p4.product_code, "", p4.description, "kg", "not-a-number"],
        ]
    )
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    assert resp.json()["error_count"] == 4


def test_oversized_quantity_flagged_not_a_500(client, auth_headers, branch_user, make_product):
    # BUG-001 boundary, reused here for the upload path specifically.
    p1 = make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg", 999999999]])
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    assert resp.json()["error_count"] == 1


def test_decimal_quantity_accepted(client, auth_headers, branch_user, make_product):
    p1 = make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg", 12.5]])
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    body = resp.json()
    assert body["valid_line_count"] == 1
    assert body["lines"][0]["quantity"] == 12.5


def test_empty_file_header_only_parses_to_zero_lines(client, auth_headers, branch_user):
    data = _xlsx_bytes([])
    resp = _upload(client, auth_headers(branch_user), data)
    assert resp.status_code == 200
    assert resp.json()["valid_line_count"] == 0


def test_corrupted_file_rejected_cleanly_not_a_500(client, auth_headers, branch_user):
    resp = _upload(client, auth_headers(branch_user), b"this is not an excel file at all")
    assert resp.status_code == 422


def test_csv_content_with_xlsx_extension_rejected_cleanly(client, auth_headers, branch_user):
    resp = _upload(client, auth_headers(branch_user), b"Product Code,Quantity\n4503253,10\n")
    assert resp.status_code == 422


def test_wrong_file_type_pdf_bytes_rejected_cleanly(client, auth_headers, branch_user):
    resp = _upload(client, auth_headers(branch_user), b"%PDF-1.4 not really a pdf either")
    assert resp.status_code == 422


def test_supplier_blocked_from_branch_only_upload_endpoint(client, auth_headers, supplier_user, make_product):
    p1 = make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg", 10]])
    resp = _upload(client, auth_headers(supplier_user), data)
    assert resp.status_code == 403


def test_unauthenticated_upload_rejected(client, make_product):
    p1 = make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg", 10]])
    resp = client.post(
        "/api/v1/orders/draft/preview-excel",
        files={"file": ("order.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert resp.status_code == 401


def test_full_flow_preview_then_save_reuses_normal_draft_path(client, auth_headers, branch_user, make_product, db_session):
    """
    The Excel upload is purely an alternate INPUT method feeding the
    existing, already-tested save-draft flow -- never a separate order-
    creation path. This proves preview -> apply -> save produces exactly
    the quantity the file specified.
    """
    # Force the order window open regardless of real wall-clock time —
    # only the save step at the end actually checks it.
    db_session.add(SystemSetting(key="branch_order_deadline", value="23:59", updated_by=branch_user.id))
    db_session.commit()

    p1 = make_product()
    data = _xlsx_bytes([[p1.product_code, "", p1.description, "kg", 12.5]])
    headers = auth_headers(branch_user)

    preview = _upload(client, headers, data)
    assert preview.status_code == 200
    lines = [
        {"product_id": ln["product_id"], "quantity": ln["quantity"]}
        for ln in preview.json()["lines"]
        if ln["error"] is None
    ]
    assert lines == [{"product_id": p1.id, "quantity": 12.5}]

    save = client.post("/api/v1/orders/draft", headers=headers, json={"lines": lines})
    assert save.status_code == 200
    body = save.json()
    assert body["status"] == "DRAFT"
    assert body["lines"][0]["quantity"] == 12.5
