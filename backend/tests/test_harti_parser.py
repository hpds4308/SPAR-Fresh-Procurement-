"""
Pure unit tests for the HARTI bulletin parser in harti_import_service —
no database, no network. The fixture bulletin's expected values are the
standalone market-price-system tool's own Excel output for that day
(output/2026.10.02.xlsx), which this parser is a port of.
"""
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.services import harti_import_service as h
from app.services.harti_import_service import PriceRange, _Word

FIXTURE = Path(__file__).parent / "fixtures" / "harti_2026-10-02.pdf"


@pytest.mark.parametrize(
    "text, expected",
    [
        ("450- 500", (450, 500)),
        ("420 - 500", (420, 500)),
        ("1,100- 1,200", (1100, 1200)),
        ("900 – 950", (900, 950)),  # en dash
        ("450", (450, 450)),  # a single price is a range with equal ends
        ("-", None),
        ("", None),
        ("120 160", None),  # no dash, two numbers — ambiguous, skipped
        ("500 - 450", None),  # min above max
    ],
)
def test_parse_price_range(text, expected):
    result = h.parse_price_range(text)
    assert (None if result is None else (result.min, result.max)) == (
        None if expected is None else tuple(Decimal(v) for v in expected)
    )


def test_market_average_is_midpoint():
    assert PriceRange(Decimal(450), Decimal(500)).average == Decimal("475.00")


def test_final_average_skips_missing_markets_and_rounds_half_up():
    # Midpoints 313.50 and 313.75 average to exactly 313.625 — the
    # standalone tool's toFixed(2) gives 313.63; Python's round() would give 313.62.
    ranges = [PriceRange(Decimal(313), Decimal(314)), PriceRange(Decimal("313.5"), Decimal(314))]
    assert h.final_average(ranges) == Decimal("313.63")
    assert h.final_average([]) is None


def test_extract_date_from_harti_filename():
    assert h.extract_date("Vegetable Pricenew ex1(2026.10.02).pdf") == date(2026, 10, 2)
    assert h.extract_date("harti_2026-09-07.pdf") == date(2026, 9, 7)
    assert h.extract_date("report.pdf") is None
    assert h.extract_date("2026.02.30.pdf") is None  # not a real date


def test_fixture_bulletin_matches_standalone_tool_output():
    bulletin = h.parse_bulletin(FIXTURE.read_bytes(), filename=FIXTURE.name)

    assert bulletin.report_date == date(2026, 10, 2)
    assert len(bulletin.rows) == 27
    assert bulletin.not_priced == []
    by_code = {r.dc_code: r for r in bulletin.rows}

    beans = by_code["4503951"]
    assert (beans.system_name, beans.pdf_name) == ("GREEN BEANS", "Beans")
    assert {k: (r.min, r.max, r.average) for k, r in beans.markets.items()} == {
        "dambulla": (450, 500, Decimal("475.00")),
        "thambuththegama": (420, 500, Decimal("460.00")),
        "nuwara_eliya": (420, 450, Decimal("435.00")),
    }
    assert beans.final_average == Decimal("456.67")

    # Only Nuwara Eliya priced cabbage that day.
    cabbage = by_code["4503948"]
    assert set(cabbage.markets) == {"nuwara_eliya"} and cabbage.final_average == Decimal("270.00")

    # A row with fewer cells than columns ("Eggplant") still lands each
    # range under the right market, by position.
    eggplant = by_code["4503763"]
    assert {k: (r.min, r.max) for k, r in eggplant.markets.items()} == {"dambulla": (260, 300), "thambuththegama": (180, 220)}
    assert eggplant.final_average == Decimal("240.00")

    # Excluded / unmapped PDF products never appear.
    assert "Cabbage (Kandy)" not in {r.pdf_name for r in bulletin.rows}
    assert {r.pdf_name for r in bulletin.rows} >= {"Beet root", "Beet root (N Eliya)", "Big-onion Local"}


def test_report_date_from_pdf_when_filename_has_none():
    bulletin = h.parse_bulletin(FIXTURE.read_bytes(), filename="upload.pdf")
    assert bulletin.report_date == date(2026, 10, 2)


def test_explicit_report_date_wins():
    bulletin = h.parse_bulletin(FIXTURE.read_bytes(), report_date=date(2026, 10, 1), filename=FIXTURE.name)
    assert bulletin.report_date == date(2026, 10, 1)


def test_not_a_pdf_is_a_clean_error():
    with pytest.raises(h.HartiImportError):
        h.parse_bulletin(b"%PDF-1.4 definitely not really a pdf", filename="x(2026.10.02).pdf")


# ---- Layout logic on synthetic word positions ----

_HEADINGS_X = {  # header center x, as in the real bulletin
    "Peliyagoda": 126,
    "Kandy": 174,
    "Dambulla": 221,
    "Meegoda": 266,
    "Norochchole": 311,
    "Thambuththegama": 358,
    "Keppetipola": 406,
    "Nuwaraeliya": 453,
    "Bandarawela": 502,
    "Veyangoda": 553,
}


def _w(text, x, y, width=10.0):
    return _Word(text=text, x0=x, x1=x + width, y=y)


def _header(y=124.0):
    return [_w(name, x - 5, y) for name, x in _HEADINGS_X.items()]


def test_later_pages_never_fill_a_product_the_table_left_blank():
    # Page 1: the real table — Capsicum is listed but blank in all four markets.
    table = _header() + [
        _w("Capsicum", 22, 200),
        _w("-", 220, 200),
        _w("-", 356, 200),
        _w("Beans", 26, 220),
        _w("450-", 205, 220),
        _w("500", 230, 220),
    ]
    # Page 2: a chart with no headings of its own, whose label normalizes
    # to "capsicum" and has a number sitting where the Dambulla column was.
    chart = [_w("Capsicum", 22, 300), _w("(%", 60, 300), _w("↑)", 72, 300), _w("254", 215, 300)]

    bulletin = h._parse_pages([table, chart], report_date=date(2026, 10, 2))

    assert [r.system_name for r in bulletin.rows] == ["GREEN BEANS"]
    assert bulletin.not_priced == ["CAPSICUM"]


def test_two_word_heading_is_found():
    # A bulletin that spells the column "Nuwara Eliya" as two words.
    header = [w for w in _header() if w.text != "Nuwaraeliya"] + [_w("Nuwara", 436, 124, 16), _w("Eliya", 455, 124, 14)]
    page = header + [_w("Carrot", 26, 200), _w("200-", 437, 200), _w("220", 465, 200)]

    bulletin = h._parse_pages([page], report_date=date(2026, 10, 2))

    assert bulletin.rows[0].markets == {"nuwara_eliya": PriceRange(Decimal(200), Decimal(220))}


def test_no_mapped_products_is_an_error():
    page = _header() + [_w("Pineapple", 22, 200), _w("350-", 205, 200), _w("400", 230, 200)]
    with pytest.raises(h.HartiImportError):
        h._parse_pages([page], report_date=date(2026, 10, 2))
