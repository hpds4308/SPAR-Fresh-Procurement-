"""
Multi-source daily import of local market reference prices, from five
public Sri Lankan produce-price sources, tried in this priority order:

1. HARTI (Hector Kobbekaduwa Agrarian Research and Training Institute) —
   government wholesale bulletin, published as a dated PDF.
2. Dambulla Dedicated Economic Center — a real JSON API behind their
   site's own price-list page (found by inspecting its JS bundle; there
   is no public API documentation for it).
3. Keppetipola Dedicated Economic Center — prices embedded directly in
   that site's HTML, no API or PDF involved.
4. Central Bank of Sri Lanka Daily Price Report — a dated PDF at a
   predictable URL, wholesale + retail prices for a smaller basket.
5. GoviSaviya — a third-party aggregator. Its own item names and market
   labels (Peliyagoda, Thambuththegama, Keppetipola, Bandarawela, Kandy,
   Dambulla) match HARTI's exactly, so this is almost certainly
   re-publishing HARTI's own data rather than an independent source —
   kept last-priority, used only to fill whatever gaps 1-4 leave.

Each source is tried independently; a failure in one (site down, format
changed) is logged and simply skipped — it never blocks the others. For
a given day, whichever source lists a product FIRST wins; later sources
only fill products the earlier ones didn't cover. Everything matched is
upserted into market_reference_prices under source="LOCAL_MARKET", for
the current price window's delivery date — the same table and date
convention AdminMarketPrices.tsx reads and writes by hand.

Runs from scripts/import_harti_prices.py (see that file for scheduling).
"""
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import date, timedelta

import pdfplumber
from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import Role, User, UserRole
from app.services import pricing_service

SOURCE = "LOCAL_MARKET"
REQUEST_TIMEOUT = 30
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; SPAR-procurement-price-import/1.0)"}


class HartiImportError(Exception):
    """Raised when EVERY source fails — the caller logs this and moves on
    rather than crashing the import loop. A single source failing does not
    raise this; it's caught and logged per-source in run_import."""


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# 1. HARTI (PDF bulletin)
# ---------------------------------------------------------------------------

_HARTI_INDEX_URL = "https://www.harti.gov.lk/daily-price.php"
_HARTI_BASE_URL = "https://www.harti.gov.lk/"

_HARTI_TO_PRODUCT_PELIYAGODA = {
    "beans": "GREEN BEANS", "carrot": "CARROTS", "leeks": "LEEKS", "beet root": "BEETROOT",
    "knolkhol": "KNOL KHOL", "raddish": "RADDISH", "cabbage (kandy)": "CABBAGE", "tomato": "TOMATOES",
    "ladies fingers": "LADIES FINGERS", "brinjals": "BRINJALS", "capsicum": "CAPSICUM", "pumpkin": "PUMPKIN",
    "cucumber": "CUCUMBER", "bitter gourd": "BITTER GOURD", "snake gourd": "SNAKE GOURD",
    "drumstick": "DRUMSTICKS", "long beans": "LONG BEANS", "ash plantains": "ASH PLANTAINS",
    "green chillies": "GREEN CHILIES", "lime": "LIME", "sweet potatoe": "SWEET POTATO",
    "manioc": "MANIOC", "eggplant": "EGG PLANTS", "ambul": "BANANA AMBUL", "kolikuttu": "BANANA KOLIKUTTU",
    "seeni": "BANANA SEENI", "papaya": "PAPAYA", "passion fruits": "PASSION FRUIT",
    "pineapple - large": "PINEAPPLE", "woodapple": "WOODAPPLE", "avocado": "AVOCADO", "orange": "ORANGE LOCAL",
}
_HARTI_PETTAH_ITEMS = {
    ("onion (rs/kg)", "vedalan"): "RED ONIONS",
    ("big onion", "imported"): "BIG ONIONS",
    ("potatoes (rs/kg)", "nuwaraeliya"): "LOCAL POTATOES",
}
_HARTI_PDF_LINK_RE = re.compile(
    r'href="(assets/pdf/food_price/daily/eng/\d{4}/[A-Za-z]+/[^"]*?\((\d{4})\.(\d{2})\.(\d{2})\)\.pdf)"'
)
_HARTI_PAGE1_DATA_RE = re.compile(r"^(.+?)\s+[\d,]+\.\d{2}\s*-\s*[\d,]+\.\d{2}\s+([\d,]+\.\d{2})")
_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)")


def _normalize_unit_suffix(label: str) -> str:
    label = re.sub(r"\s+", " ", label).strip()
    label = re.sub(r"\(rs[^)]*\)?", "", label, flags=re.IGNORECASE).strip()
    return label.lower()


def _harti_find_latest_bulletin() -> tuple[date, str]:
    html = _get(_HARTI_INDEX_URL).decode("utf-8", errors="ignore")
    matches = _HARTI_PDF_LINK_RE.findall(html)
    if not matches:
        raise RuntimeError("No dated PDF links found on the HARTI index page — page format may have changed.")
    parsed = [(date(int(y), int(m), int(d)), href) for href, y, m, d in matches]
    parsed.sort(reverse=True)
    latest_date, href = parsed[0]
    return latest_date, urllib.parse.urljoin(_HARTI_BASE_URL, urllib.parse.quote(href))


def _harti_parse_peliyagoda_table(page) -> dict[str, float]:
    tables = page.extract_tables()
    if not tables:
        return {}
    out = {}
    for row in tables[0]:
        if not row or not row[0]:
            continue
        norm = _normalize_unit_suffix(row[0])
        product = _HARTI_TO_PRODUCT_PELIYAGODA.get(norm)
        if not product:
            continue
        cell = row[1] if len(row) > 1 and row[1] else ""
        m = _RANGE_RE.search(cell)
        if not m:
            continue
        lo, hi = float(m.group(1)), float(m.group(2))
        out[product] = round((lo + hi) / 2, 2)
    return out


def _harti_parse_pettah_table(page) -> dict[str, float]:
    text = page.extract_text() or ""
    section = None
    out = {}
    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        m = _HARTI_PAGE1_DATA_RE.match(line)
        if m:
            label = m.group(1).strip().lower()
            if section and (section, label) in _HARTI_PETTAH_ITEMS:
                out[_HARTI_PETTAH_ITEMS[(section, label)]] = float(m.group(2).replace(",", ""))
        elif not line.endswith("-") and re.search(r"\d", line) is None:
            section = line.strip().lower()
    return out


def _fetch_harti() -> dict[str, float]:
    _, pdf_url = _harti_find_latest_bulletin()
    pdf_bytes = _get(pdf_url)
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) < 2:
            raise RuntimeError(f"Expected at least 2 pages in the HARTI bulletin, got {len(pdf.pages)}.")
        prices = _harti_parse_pettah_table(pdf.pages[0])
        prices.update(_harti_parse_peliyagoda_table(pdf.pages[1]))
    if not prices:
        raise RuntimeError("Parsed the HARTI bulletin but matched zero known items — format may have changed.")
    return prices


# ---------------------------------------------------------------------------
# 2. Dambulla Dedicated Economic Center (JSON API)
# ---------------------------------------------------------------------------

_DAMBULLA_API = "https://api.dambulladec.com/api/prices/by-date/{date}?page=1&limit=300"

_DAMBULLA_TO_PRODUCT = {
    "king coconut": "KING COCONUT", "water spinach": "KANKUN", "ambarella": "AMBARELLA",
    "ash plantain": "ASH PLANTAINS", "avacado": "AVOCADO", "banana - abul": "BANANA AMBUL",
    "banana - ambun": "BANANA AMBUN", "banana - kolikuttu": "BANANA KOLIKUTTU", "banana - sini": "BANANA SEENI",
    "beans": "GREEN BEANS", "beetroot - nuwaraeliya": "BEETROOT", "beetroot cut - malsiripura": "Cut Beetroot",
    "big onion import": "BIG ONIONS", "bitter gourd": "BITTER GOURD", "brinjal": "BRINJALS",
    "cabbage": "CABBAGE", "capsicum": "CAPSICUM", "cauliflower": "CAULIFLOWER", "chaw - chaw": "CHOW CHOW",
    "coconut": "COCONUTS", "cooking melon": "KEKIRI", "corns": "CORN", "cucumber": "CUCUMBER",
    "curry leaves": "CURRY LEAVES", "drumsticks": "DRUMSTICKS", "eggplant": "EGG PLANTS", "garlic": "GARLIC",
    "ginger": "GINGER", "gooseberry": "NELLI", "gotukola": "GOTUKOLA", "green chili": "GREEN CHILIES",
    "guava": "GUAVA", "indian bael": "BELI", "kiriala": "KIRIALA", "kohila": "KOHILA",
    "lady's fingers": "LADIES FINGERS", "leeks": "LEEKS", "lime": "LIME", "lotus roots": "LOTUS YAM",
    "mango- tjc": "MANGO TJC GRADE 1", "manioc": "MANIOC", "mukunuwenna": "MUKUNUWENNA",
    "nai miris": "NI MIRIS", "nnolkhol": "KNOL KHOL", "nuwaraeliya carrot": "CARROTS",
    "onion leaves": "ONION LEAVES", "papaya": "PAPAYA", "passion": "PASSION FRUIT",
    "pineapple": "PINEAPPLE", "plantain flower": "PLANTAIN FLOWER", "potatoes - import": "POTATOES",
    "potatoes - nuwaraeliya": "LOCAL POTATOES", "pumpkin - big": "PUMPKIN", "pumpkin - malashian": "MINI PUMPKIN",
    "raddish": "RADDISH", "red banana": "BANANA RED", "red cabbage": "RED CABBAGE",
    "red onion- lanka": "RED ONIONS", "ridge gourd": "RIBBED GOURD", "snake gourd": "SNAKE GOURD",
    "soursop": "KATU ANODA", "sweet potato": "SWEET POTATO", "tamarind": "TAMARIND",
    "thithbatu": "THALANA BATU", "thumbakarawila": "THUMBA KARAWILA", "tomato": "TOMATOES",
    "watermelon": "MELON CHINESE (WATER MELON)", "winged bean": "DAMBALA", "woodapple": "WOODAPPLE",
    "yard - long beans": "LONG BEANS",
}


def _fetch_dambulla_dec() -> dict[str, float]:
    today = date.today()
    items: list = []
    for offset in range(7):  # today, then back a week — the site sometimes lags several days
        url = _DAMBULLA_API.format(date=(today - timedelta(days=offset)).isoformat())
        body = json.loads(_get(url))
        items = body.get("data") or []
        if items:
            break
    if not items:
        raise RuntimeError("Dambulla DEC API returned no items for the last 7 days.")

    out: dict[str, float] = {}
    for it in items:
        name = (it.get("product") or {}).get("name", "").strip().lower()
        product = _DAMBULLA_TO_PRODUCT.get(name)
        if not product or product in out:
            continue
        lo, hi = it.get("min_price"), it.get("max_price")
        if lo is None or hi is None:
            continue
        out[product] = round((float(lo) + float(hi)) / 2, 2)
    if not out:
        raise RuntimeError("Parsed the Dambulla DEC API but matched zero known items — check the mapping.")
    return out


# ---------------------------------------------------------------------------
# 3. Keppetipola Dedicated Economic Center (HTML)
# ---------------------------------------------------------------------------

_KEPPETIPOLA_URL = "https://www.deckeppetipola.com/price-list.php"
_KEPPETIPOLA_ITEM_RE = re.compile(
    r'<h4>\s*([^<]+?)\s*</h4>\s*<div class="price">රු:\s*([^<]*?)\s*</div>', re.DOTALL
)
_KEPPETIPOLA_TO_PRODUCT = {
    "beans": "GREEN BEANS", "beetroot": "BEETROOT", "beetroot cut": "Cut Beetroot", "brinjal": "BRINJALS",
    "cabbage": "CABBAGE", "cauliflower": "CAULIFLOWER", "red cabbage": "RED CABBAGE",
    "capsicum": "CAPSICUM", "carrot": "CARROTS", "cucumber": "CUCUMBER", "green chili": "GREEN CHILIES",
    "nookal": "KNOL KHOL", "leeks": "LEEKS", "potatoes - walimada": "LOCAL POTATOES",
    "potatoes - import": "POTATOES", "pumpkin - malaysian": "MINI PUMPKIN", "raddish": "RADDISH",
    "tomato": "TOMATOES", "bell pepper -red": "BELL PEPPER RED", "bell pepper - green": "BELL PEPPER GREEN",
    "bell pepper - yellow": "BELL PEPPER YELLOW", "parsleys": "PARSLEY", "celery": "CELERY",
    "mint leaves": "MINCHI LEAVES", "coriander-leaves": "CORIANDER LEAVES", "iceberg": "ICEBERG (LETTUCE)",
    "cooking melon": "KEKIRI", "ridge gourd": "RIBBED GOURD", "lady's fingers": "LADIES FINGERS",
    "snake gourd": "SNAKE GOURD", "bitter gourd": "BITTER GOURD", "thumbakarawila": "THUMBA KARAWILA",
    "thibbatu": "THALANA BATU", "bolabatu": "TIB BATU", "winged bean": "DAMBALA",
    "yard- long beans": "LONG BEANS", "drumsticks": "DRUMSTICKS", "ash plantain": "ASH PLANTAINS",
    "plantain flower": "PLANTAIN FLOWER", "ambarella": "AMBARELLA", "lime": "LIME", "nai miris": "NI MIRIS",
    "genger": "GINGER", "small onions - lanka": "RED ONIONS", "b-onion - import": "BIG ONIONS",
    "kohila": "KOHILA", "manioc": "MANIOC", "sweet potato": "SWEET POTATO", "onion leaves": "ONION LEAVES",
    "mukunuwenna": "MUKUNUWENNA", "gotukola": "GOTUKOLA", "curry leaves": "CURRY LEAVES",
    "spinach": "NIVITHI", "water spinach": "KANKUN", "banana -sini": "BANANA SEENI",
    "banana - abul": "BANANA AMBUL", "kolikuttu": "BANANA KOLIKUTTU", "coconut": "COCONUTS",
    "tamarind": "TAMARIND", "avocado": "AVOCADO", "woodapple": "WOODAPPLE",
    "watermelon": "MELON CHINESE (WATER MELON)", "papaya": "PAPAYA",
    "mango - karathakolomban": "MANGO K/C", "cooking mango": "MANGO CURRY",
}


def _fetch_keppetipola_dec() -> dict[str, float]:
    html = _get(_KEPPETIPOLA_URL).decode("utf-8", errors="ignore")
    out: dict[str, float] = {}
    for raw_name, raw_price in _KEPPETIPOLA_ITEM_RE.findall(html):
        name = raw_name.strip().lower()
        product = _KEPPETIPOLA_TO_PRODUCT.get(name)
        if not product or product in out:
            continue
        price_text = raw_price.strip()
        if not price_text:
            continue  # blank = not available today
        m = _RANGE_RE.search(price_text)
        if m:
            price = round((float(m.group(1)) + float(m.group(2))) / 2, 2)
        else:
            m_single = re.search(r"\d+(?:\.\d+)?", price_text)
            if not m_single:
                continue
            price = float(m_single.group())
        out[product] = price
    if not out:
        raise RuntimeError("Parsed the Keppetipola DEC page but matched zero known items — page format may have changed.")
    return out


# ---------------------------------------------------------------------------
# 4. Central Bank of Sri Lanka Daily Price Report (PDF, dated URL)
# ---------------------------------------------------------------------------

_CBSL_URL_TEMPLATE = (
    "https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/statistics/pricerpt/price_report_{date}_e.pdf"
)
_CBSL_TO_PRODUCT = {
    "beans": "GREEN BEANS", "carrot": "CARROTS", "cabbage": "CABBAGE", "tomato": "TOMATOES",
    "brinjal": "BRINJALS", "pumpkin": "PUMPKIN", "snake gourd": "SNAKE GOURD",
    "green chilli": "GREEN CHILIES", "lime": "LIME", "red onion (local)": "RED ONIONS",
    "big onion (imp)": "BIG ONIONS", "potato (local)": "LOCAL POTATOES", "potato (imp)": "POTATOES",
    "coconut (avg.)": "COCONUTS", "banana (sour)": "BANANA AMBUL", "papaw": "PAPAYA",
}
# Item Unit <10 numeric tokens>: Pettah-WS-Yest, Pettah-WS-Today, Dambulla-WS-Yest,
# Dambulla-WS-Today, Pettah-Retail-Yest, Pettah-Retail-Today, ... — we use Pettah
# Retail Today (index 5), falling back to Pettah Wholesale Today (index 1) if n.a.
_CBSL_LINE_RE = re.compile(r"^(.+?)\s+Rs\./\S+\s+(.+)$")
_CBSL_TOKEN_RE = re.compile(r"(\d[\d,\s]*\.\d{2}|n\.a\.)")


def _cbsl_parse_tokens(rest: str) -> list[str]:
    return _CBSL_TOKEN_RE.findall(rest)


def _fetch_cbsl() -> dict[str, float]:
    today = date.today()
    pdf_bytes = None
    for offset in range(7):  # today, then back a week — reports aren't always published same-day
        url = _CBSL_URL_TEMPLATE.format(date=(today - timedelta(days=offset)).strftime("%Y%m%d"))
        try:
            pdf_bytes = _get(url)
            break
        except Exception:
            continue
    if pdf_bytes is None:
        raise RuntimeError("Could not find a CBSL price report in the last 7 days at the expected URL.")

    out: dict[str, float] = {}
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) < 2:
            raise RuntimeError(f"Expected at least 2 pages in the CBSL report, got {len(pdf.pages)}.")
        text = pdf.pages[1].extract_text() or ""
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            m = _CBSL_LINE_RE.match(line)
            if not m:
                continue
            label = m.group(1).strip().lower()
            product = _CBSL_TO_PRODUCT.get(label)
            if not product or product in out:
                continue
            tokens = _cbsl_parse_tokens(m.group(2))
            if len(tokens) < 6:
                continue
            for idx in (5, 1):  # Pettah retail today, else Pettah wholesale today
                raw = tokens[idx].replace(" ", "").replace(",", "")
                if raw != "n.a.":
                    out[product] = float(raw)
                    break
    if not out:
        raise RuntimeError("Parsed the CBSL report but matched zero known items — format may have changed.")
    return out


# ---------------------------------------------------------------------------
# 5. GoviSaviya (aggregator JSON API) — lowest priority, fills gaps only
# ---------------------------------------------------------------------------

_GOVISAVIYA_URL = "https://govisaviya.lk/api/prices/homepage"
_GOVISAVIYA_TO_PRODUCT = {
    "capsicum": "CAPSICUM", "raddish": "RADDISH", "tomato": "TOMATOES", "brinjals": "BRINJALS",
    "cucumber": "CUCUMBER", "green chillies": "GREEN CHILIES", "leeks": "LEEKS", "beans": "GREEN BEANS",
    "carrot": "CARROTS", "drumstick": "DRUMSTICKS", "bitter gourd": "BITTER GOURD",
    "ladies fingers": "LADIES FINGERS", "pumpkin": "PUMPKIN", "sweet potatoe": "SWEET POTATO",
    "eggplant": "EGG PLANTS", "long beans": "LONG BEANS", "knolkhol": "KNOL KHOL",
    "b'onion imported": "BIG ONIONS", "luffa": "RIBBED GOURD", "snake gourd": "SNAKE GOURD",
    "manioc": "MANIOC", "ash plantains": "ASH PLANTAINS", "beet root": "BEETROOT", "lime": "LIME",
    "potato(imported)": "POTATOES", "potato (nuwaraeliya)": "LOCAL POTATOES", "cabbage (n'eliya)": "CABBAGE",
    "ambul": "BANANA AMBUL", "papaya": "PAPAYA", "seeni": "BANANA SEENI", "kolikuttu": "BANANA KOLIKUTTU",
    "avocado": "AVOCADO", "orange": "ORANGE LOCAL", "pineapple large": "PINEAPPLE", "woodapple": "WOODAPPLE",
    "big-onion local": "BIG ONIONS",
}


def _fetch_govisaviya() -> dict[str, float]:
    body = json.loads(_get(_GOVISAVIYA_URL))
    items = body.get("data") or []
    out: dict[str, float] = {}
    for it in items:
        name = str(it.get("item", "")).strip().lower()
        product = _GOVISAVIYA_TO_PRODUCT.get(name)
        price = it.get("latestPrice")
        if not product or price is None or product in out:
            continue
        out[product] = float(price)
    if not out:
        raise RuntimeError("Parsed the GoviSaviya API but matched zero known items — check the mapping.")
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

_SOURCES = [
    ("HARTI", _fetch_harti),
    ("Dambulla DEC", _fetch_dambulla_dec),
    ("Keppetipola DEC", _fetch_keppetipola_dec),
    ("CBSL", _fetch_cbsl),
    ("GoviSaviya", _fetch_govisaviya),
]


def _find_an_admin(db: Session) -> User | None:
    return (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.code == "ADMIN", User.is_active.is_(True))
        .order_by(User.id)
        .first()
    )


def run_import(db: Session) -> dict:
    """
    Runs every source in priority order, merging results (first source to
    list a product wins for that day), and upserts everything matched into
    market_reference_prices under source=LOCAL_MARKET, for the current
    price window's delivery date. A source that fails is logged in the
    returned summary and skipped — it never blocks the others. Raises
    HartiImportError only if EVERY source failed.
    """
    admin = _find_an_admin(db)
    if not admin:
        raise HartiImportError("No active ADMIN account found to attribute this import to.")

    merged: dict[str, float] = {}
    contributed: dict[str, int] = {}
    failures: dict[str, str] = {}
    for name, fetch_fn in _SOURCES:
        try:
            prices = fetch_fn()
        except Exception as e:
            failures[name] = str(e)
            continue
        added = 0
        for product, price in prices.items():
            if product not in merged:
                merged[product] = price
                added += 1
        contributed[name] = added

    if not merged:
        raise HartiImportError(f"Every source failed: {failures}")

    products = {p.description: p.id for p in db.query(Product).filter(Product.description.in_(merged.keys())).all()}

    delivery_date = pricing_service.get_price_window(db).delivery_date
    saved = 0
    for description, price in merged.items():
        product_id = products.get(description)
        if not product_id:
            continue
        pricing_service.set_reference_price(db, admin, product_id, delivery_date, price, SOURCE)
        saved += 1

    return {
        "delivery_date": delivery_date.isoformat(),
        "matched": len(merged),
        "saved": saved,
        "contributed": contributed,
        "failures": failures,
    }
