"""
DB-backed tests for the HARTI Local Market Prices import — saving a
bulletin (replace-by-date, LOCAL_MARKET reference prices for Price
History) and the Admin API (view, sync, upload, Excel export).
"""
import io
from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from app.models.local_market_price import LocalMarketPrice
from app.models.market_reference_price import MarketReferencePrice
from app.services import harti_import_service as h
from app.services.harti_import_service import Bulletin, BulletinRow, PriceRange

FIXTURE = Path(__file__).parent / "fixtures" / "harti_2026-10-02.pdf"
DAY = date(2026, 10, 2)


def _range(low, high):
    return PriceRange(Decimal(low), Decimal(high))


def _bulletin(report_date=DAY, **rows_by_code):
    """rows_by_code: dc_code → {market_key: (min, max)}."""
    names = {m.dc_code: (label, m.system_name) for label, m in h.PRODUCT_MAPPING.items() if m}
    return Bulletin(
        report_date=report_date,
        rows=[
            BulletinRow(
                dc_code=code,
                system_name=names[code][1],
                pdf_name=names[code][0],
                markets={k: _range(*v) for k, v in markets.items()},
            )
            for code, markets in rows_by_code.items()
        ],
    )


def _reference_prices(db_session, source="LOCAL_MARKET"):
    rows = db_session.query(MarketReferencePrice).filter(MarketReferencePrice.source == source).all()
    return {(r.product_id, r.delivery_date): r.price for r in rows}


@pytest.fixture
def admin(make_user):
    return make_user(role="ADMIN")


@pytest.fixture
def beans(make_product):
    return make_product(product_code="4503951", description="GREEN BEANS")


@pytest.fixture
def carrots(make_product):
    return make_product(product_code="4503950", description="CARROTS")


def test_save_writes_ranges_and_final_average_reference_price(db_session, admin, beans):
    result = h.save_bulletin(
        db_session,
        admin,
        _bulletin(**{"4503951": {"dambulla": (450, 500), "thambuththegama": (420, 500), "nuwara_eliya": (420, 450)}}),
    )

    assert result == {"report_date": DAY, "saved": 1, "not_priced": [], "unmatched": []}
    row = db_session.query(LocalMarketPrice).one()
    assert (row.product_id, row.dc_code, row.system_name, row.pdf_name) == (beans.id, "4503951", "GREEN BEANS", "Beans")
    assert (row.dambulla_min, row.dambulla_max) == (450, 500)
    assert (row.keppetipola_min, row.keppetipola_max) == (None, None)
    assert row.final_average == Decimal("456.67")
    assert _reference_prices(db_session) == {(beans.id, DAY): Decimal("456.67")}


def test_dc_code_missing_from_products_is_saved_but_reported(db_session, admin):
    result = h.save_bulletin(db_session, admin, _bulletin(**{"4503950": {"dambulla": (160, 220)}}))

    assert result["unmatched"] == [{"dc_code": "4503950", "system_name": "CARROTS"}]
    assert db_session.query(LocalMarketPrice).one().product_id is None
    assert _reference_prices(db_session) == {}


def test_reimport_replaces_that_date_only(db_session, admin, beans, carrots):
    other_day = date(2026, 10, 1)
    h.save_bulletin(db_session, admin, _bulletin(other_day, **{"4503951": {"dambulla": (100, 200)}}))
    h.save_bulletin(
        db_session, admin, _bulletin(**{"4503951": {"dambulla": (450, 500)}, "4503950": {"dambulla": (160, 220)}})
    )
    db_session.add(
        MarketReferencePrice(
            product_id=carrots.id, source="KEELLS", delivery_date=DAY, price=300, updated_by=admin.id, updated_at=admin.created_at
        )
    )
    db_session.commit()

    h.save_bulletin(db_session, admin, _bulletin(**{"4503951": {"dambulla": (500, 600)}}))

    today_rows = db_session.query(LocalMarketPrice).filter(LocalMarketPrice.report_date == DAY).all()
    assert [(r.dc_code, r.final_average) for r in today_rows] == [("4503951", Decimal("550.00"))]
    assert _reference_prices(db_session) == {(beans.id, other_day): Decimal("150.00"), (beans.id, DAY): Decimal("550.00")}
    assert _reference_prices(db_session, "KEELLS") == {(carrots.id, DAY): Decimal("300.00")}


# ---- API ----


def test_get_defaults_to_newest_report(client, db_session, admin, beans, auth_headers):
    h.save_bulletin(db_session, admin, _bulletin(date(2026, 9, 30), **{"4503951": {"dambulla": (100, 200)}}))
    h.save_bulletin(
        db_session, admin, _bulletin(**{"4503951": {"dambulla": (450, 500), "nuwara_eliya": (420, 450)}})
    )

    body = client.get("/api/v1/local-market-prices", headers=auth_headers(admin)).json()

    assert body["report_date"] == "2026-10-02"
    assert body["available_dates"] == ["2026-10-02", "2026-09-30"]
    [row] = body["rows"]
    assert row["dc_code"] == "4503951" and row["system_name"] == "GREEN BEANS" and row["pdf_name"] == "Beans"
    assert row["category_name"] == "Test Category"
    assert row["dambulla"] == {"min": 450.0, "max": 500.0, "average": 475.0}
    assert row["thambuththegama"] is None and row["keppetipola"] is None
    assert row["nuwara_eliya"] == {"min": 420.0, "max": 450.0, "average": 435.0}
    assert row["final_average"] == 455.0

    older = client.get("/api/v1/local-market-prices?report_date=2026-09-30", headers=auth_headers(admin)).json()
    assert older["report_date"] == "2026-09-30" and older["rows"][0]["final_average"] == 150.0


def test_get_with_nothing_imported(client, admin, auth_headers):
    body = client.get("/api/v1/local-market-prices", headers=auth_headers(admin)).json()
    assert body == {"report_date": None, "imported_at": None, "available_dates": [], "rows": []}


def test_upload_bulletin_then_export(client, db_session, admin, beans, auth_headers):
    res = client.post(
        "/api/v1/local-market-prices/upload",
        headers=auth_headers(admin),
        files={"file": ("Vegetable Pricenew ex1(2026.10.02).pdf", FIXTURE.read_bytes(), "application/pdf")},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["report_date"] == "2026-10-02" and body["saved"] == 27
    assert len(body["unmatched"]) == 26  # only GREEN BEANS exists in this test database
    assert _reference_prices(db_session) == {(beans.id, DAY): Decimal("456.67")}

    export = client.get("/api/v1/local-market-prices/export?report_date=2026-10-02", headers=auth_headers(admin))
    assert export.status_code == 200
    assert 'filename="2026.10.02.xlsx"' in export.headers["content-disposition"]
    sheet = openpyxl.load_workbook(io.BytesIO(export.content)).active
    rows = list(sheet.iter_rows(values_only=True))
    assert rows[0][:5] == ("Date", "DC Code", "System Product", "PDF Product", "Dambulla Min")
    assert rows[0][-1] == "Final Average" and len(rows[0]) == 17
    assert rows[1] == (
        "2026-10-02", "4503951", "GREEN BEANS", "Beans",
        450, 500, 475, 420, 500, 460, None, None, None, 420, 450, 435, 456.67,
    )
    assert len(rows) == 28


def test_upload_rejects_a_non_pdf(client, admin, auth_headers):
    res = client.post(
        "/api/v1/local-market-prices/upload",
        headers=auth_headers(admin),
        files={"file": ("prices.xlsx", b"PK\x03\x04 not a pdf", "application/octet-stream")},
    )
    assert res.status_code == 422
    assert "not a PDF" in res.json()["detail"]


def test_export_with_nothing_imported_is_404(client, admin, auth_headers):
    assert client.get("/api/v1/local-market-prices/export", headers=auth_headers(admin)).status_code == 404


def test_sync_saves_latest_bulletin_as_current_admin(client, db_session, admin, beans, auth_headers, monkeypatch):
    monkeypatch.setattr(h, "fetch_latest_bulletin", lambda: _bulletin(**{"4503951": {"dambulla": (450, 500)}}))

    res = client.post("/api/v1/local-market-prices/sync", headers=auth_headers(admin))

    assert res.status_code == 200, res.text
    assert res.json() == {"report_date": "2026-10-02", "saved": 1, "not_priced": [], "unmatched": []}
    assert db_session.query(LocalMarketPrice).one().imported_by == admin.id


def test_sync_failure_is_a_clean_error_and_keeps_existing_prices(client, db_session, admin, beans, auth_headers, monkeypatch):
    h.save_bulletin(db_session, admin, _bulletin(**{"4503951": {"dambulla": (450, 500)}}))

    def _down():
        raise h.HartiImportError("Could not reach harti.gov.lk (timed out).")

    monkeypatch.setattr(h, "fetch_latest_bulletin", _down)
    res = client.post("/api/v1/local-market-prices/sync", headers=auth_headers(admin))

    assert res.status_code == 422
    assert "harti.gov.lk" in res.json()["detail"]
    assert db_session.query(LocalMarketPrice).count() == 1


def test_admin_only(client, make_user, make_branch, auth_headers):
    branch_user = make_user(role="BRANCH", branch=make_branch())
    assert client.get("/api/v1/local-market-prices", headers=auth_headers(branch_user)).status_code == 403
    assert client.post("/api/v1/local-market-prices/sync", headers=auth_headers(branch_user)).status_code == 403
