"""
Automated Keells retail price scrape — replaces running the standalone
Playwright scraper.js by hand and uploading its Excel output. The
scraping/matching logic below (REQUIRED_PRODUCTS, name normalization,
KNOWN_MATCHES, the "View All" + pagination walk, the CSS selectors) is a
line-for-line port of that reference script into this backend's own
Python/Playwright stack, so results should match what the standalone
script used to produce.

Scrapes keellssuper.com's Local Fruits and Fresh Vegetables listing pages,
matches products by name against a fixed DC-code/system-name reference
list, and upserts a KEELLS reference price for each match through
pricing_service.set_reference_price — the same table and semantics manual
entry on AdminKeellsPrices.tsx uses.

Runs two ways:
1. scripts/import_keells_prices.py — a long-running worker (see that file
   for scheduling), same pattern as scripts/import_harti_prices.py.
2. POST /pricing/reference/keells-sync — an admin-triggered immediate
   run, for refreshing today's prices without waiting on the schedule.
"""
import re
from datetime import date

from sqlalchemy.orm import Session

from app.models.product import Product
from app.models.user import Role, User, UserRole
from app.services import pricing_service

SOURCE = "KEELLS"

LOCAL_FRUITS_URL = "https://www.keellssuper.com/local-fruits"
FRESH_VEGETABLES_URL = "https://www.keellssuper.com/fresh-vegetables"

NAME_SELECTOR = ".product-card-nameV2"
PRICE_SELECTOR = ".product-card-final-priceV2"
ARROW_SELECTOR = "button.page-number-button-arrow"


class KeellsScrapeError(Exception):
    """Raised when the scrape can't produce any matched prices at all (site
    down, layout changed, zero matches) — the caller (script or API route)
    logs/surfaces this and moves on rather than crashing."""


# =============================================================
# REQUIRED PRODUCTS — DC CODE + EXACT SYSTEM NAME
# Ported as-is from the reference scraper.js.
# =============================================================

REQUIRED_PRODUCTS = [
    # ---- Local Fruits ----
    {"dc_code": "4503253", "system_name": "AVOCADO"},
    {"dc_code": "4504004", "system_name": "BANANA AMBUL"},
    {"dc_code": "4504005", "system_name": "BANANA AMBUN"},
    {"dc_code": "4504006", "system_name": "BANANA CAVENDISH"},
    {"dc_code": "4504008", "system_name": "BANANA KOLIKUTTU"},
    {"dc_code": "4504010", "system_name": "BANANA SEENI"},
    {"dc_code": "4503251", "system_name": "BELI"},
    {"dc_code": "4504494", "system_name": "DRAGON FRUIT"},
    {"dc_code": "4504495", "system_name": "DURIAN"},
    {"dc_code": "4503255", "system_name": "GUAVA"},
    {"dc_code": "4503259", "system_name": "KATU ANODA"},
    {"dc_code": "4503270", "system_name": "MANGO K/C"},
    {"dc_code": "4503272", "system_name": "MANGO TJC GRADE 1"},
    {"dc_code": "4503274", "system_name": "MANGOSTEEN"},
    {"dc_code": "4503277", "system_name": "MELON DARK BELL"},
    {"dc_code": "4503281", "system_name": "MELON RED FANTASY"},
    {"dc_code": "4503284", "system_name": "ORANGE LOCAL"},
    {"dc_code": "4503285", "system_name": "PAPAYA"},
    # PAPAYA TANNING intentionally excluded — not found on Keells.
    {"dc_code": "4503287", "system_name": "PASSION FRUIT"},
    {"dc_code": "4503289", "system_name": "PINEAPPLE"},
    {"dc_code": "4503291", "system_name": "RAMBUTAN"},
    {"dc_code": "4503298", "system_name": "WOODAPPLE"},
    # ---- Fresh Vegetables ----
    {"dc_code": "4504039", "system_name": "AMBARELLA"},
    {"dc_code": "4504012", "system_name": "ASH PLANTAINS"},
    {"dc_code": "4503211", "system_name": "BIG ONIONS"},
    {"dc_code": "4504015", "system_name": "BITTER GOURD"},
    {"dc_code": "4504016", "system_name": "BRINJALS"},
    {"dc_code": "4503775", "system_name": "COCONUTS"},
    {"dc_code": "4504017", "system_name": "CUCUMBER"},
    {"dc_code": "4504020", "system_name": "DRUMSTICKS"},
    {"dc_code": "4503212", "system_name": "GARLIC"},
    {"dc_code": "4504021", "system_name": "GINGER"},
    {"dc_code": "4503764", "system_name": "GREEN CHILIES"},
    {"dc_code": "4504026", "system_name": "LADIES FINGERS"},
    {"dc_code": "4504029", "system_name": "LIME"},
    {"dc_code": "4503767", "system_name": "LONG BEANS"},
    {"dc_code": "4503770", "system_name": "ONION LEAVES"},
    {"dc_code": "4504033", "system_name": "PUMPKIN"},
    {"dc_code": "4503771", "system_name": "RED ONIONS"},
    {"dc_code": "4503215", "system_name": "RED ONIONS PREMIUM PACK"},
    {"dc_code": "4504034", "system_name": "RIBBED GOURD"},
    {"dc_code": "4504035", "system_name": "SNAKE GOURD"},
    {"dc_code": "4503772", "system_name": "SWEET POTATO"},
    {"dc_code": "4503773", "system_name": "THALANA BATU"},
    {"dc_code": "4503947", "system_name": "BEETROOT"},
    {"dc_code": "4503962", "system_name": "BELL PEPPER GREEN"},
    {"dc_code": "4503963", "system_name": "BELL PEPPER RED"},
    {"dc_code": "4503964", "system_name": "BELL PEPPER YELLOW"},
    {"dc_code": "4503965", "system_name": "BROCCOLI"},
    {"dc_code": "4503948", "system_name": "CABBAGE"},
    {"dc_code": "4503949", "system_name": "CAPSICUM"},
    {"dc_code": "4503950", "system_name": "CARROTS"},
    {"dc_code": "4503970", "system_name": "CAULIFLOWER"},
    {"dc_code": "4503951", "system_name": "GREEN BEANS"},
    {"dc_code": "4503952", "system_name": "KNOL KHOL"},
    {"dc_code": "4503953", "system_name": "LEEKS"},
    {"dc_code": "4503954", "system_name": "LOCAL POTATOES"},
    {"dc_code": "4503955", "system_name": "RADDISH"},
    {"dc_code": "4503956", "system_name": "SALAD CUCUMBER"},
    {"dc_code": "4504000", "system_name": "SALAD LEAVES"},
    {"dc_code": "4504011", "system_name": "TOMATOES"},
]

# =============================================================
# SPECIFIC KNOWN MATCHES (system name -> possible Keells names)
# =============================================================

KNOWN_MATCHES: dict[str, list[str]] = {
    "BANANA AMBUL": ["BANANA AMBUL"],
    "BANANA AMBUN": ["BANANA AMBUN"],
    "BANANA CAVENDISH": ["BANANA CAVENDISH"],
    "BANANA KOLIKUTTU": ["BANANA KOLIKUTTU"],
    "BANANA SEENI": ["BANANA SEENI"],
    "MANGO TJC GRADE 1": ["MANGO TJC"],
    "ORANGE LOCAL": ["ORANGE LOCAL"],
    "MELON DARK BELL": ["MELON DARK BELL"],
    "MELON RED FANTASY": ["MELON RED FANTASY"],
    "COCONUTS": ["COCONUT"],
    "CARROTS": ["CARROT"],
    "RED ONIONS PREMIUM PACK": ["PRE PACKED RED ONIONS", "PRE PACKED RED ONION"],
    "LOCAL POTATOES": ["POTATOES", "POTATO"],
}

_PRICE_RE = re.compile(r"Rs\s*([\d,]+(?:\.\d+)?)")


def _normalize_name(name: str) -> str:
    name = name.upper()
    name = re.sub(r"[-_]", " ", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip()


def _match_product(system_name: str, keells_name: str) -> bool:
    system = _normalize_name(system_name)
    keells = _normalize_name(keells_name)

    if system == keells:
        return True

    for possible in KNOWN_MATCHES.get(system_name, []):
        if keells == _normalize_name(possible):
            return True

    # Simple singular/plural fallback (ASH PLANTAINS / ASH PLANTAIN, etc.)
    singular_system = system[:-1] if system.endswith("S") else system
    singular_keells = keells[:-1] if keells.endswith("S") else keells
    return singular_system == singular_keells


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    return round(value, 2) if value > 0 else None


def _scrape_category(page, url: str, category: str, needs_view_all: bool) -> list[dict]:
    """Returns a de-duplicated (by name+price) list of {category, name,
    price} for one category page, walking every page of results the same
    way the reference scraper does: click "View All" first if needed, then
    repeatedly click the right pagination arrow until it disappears."""
    page.goto(url, wait_until="domcontentloaded", timeout=60_000)

    if needs_view_all:
        # The page is a client-rendered SPA — how long the "View All"
        # button takes to appear varies a lot run to run (observed
        # anywhere from under a second to several seconds), so this polls
        # for it rather than sleeping a fixed amount before checking; a
        # fixed short sleep here was found to miss it intermittently.
        view_all = page.get_by_role("button", name="View All", exact=True)
        try:
            view_all.first.wait_for(state="visible", timeout=20_000)
        except Exception:
            return []  # never appeared — same as "not found" before
        view_all.first.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        view_all.first.click(force=True)
        page.wait_for_timeout(1500)
        page.locator(NAME_SELECTOR).first.wait_for(state="visible", timeout=20_000)
        page.wait_for_timeout(500)
    else:
        page.locator(NAME_SELECTOR).first.wait_for(state="visible", timeout=20_000)

    products: dict[str, dict] = {}

    while True:
        page.locator(NAME_SELECTOR).first.wait_for(state="visible", timeout=15_000)
        page.wait_for_timeout(500)

        name_elements = page.locator(NAME_SELECTOR)
        count = name_elements.count()

        for i in range(count):
            name_el = name_elements.nth(i)
            name = (name_el.text_content() or "").strip()
            if not name:
                continue

            card = name_el.locator("..")
            try:
                price = (card.locator(PRICE_SELECTOR).text_content() or "").strip()
            except Exception:
                price = ""
            if not price:
                continue

            key = f"{name}|{price}"
            if key not in products:
                products[key] = {"category": category, "name": name, "price": price}

        next_button = None
        arrow_buttons = page.locator(ARROW_SELECTOR)
        for i in range(arrow_buttons.count()):
            button = arrow_buttons.nth(i)
            img = button.locator("img")
            if img.count() == 0:
                continue
            src = img.first.get_attribute("src")
            if src and "right" in src.lower():
                next_button = button
                break

        if next_button is None:
            break

        old_first = (page.locator(NAME_SELECTOR).first.text_content() or "").strip()
        old_count = page.locator(NAME_SELECTOR).count()

        next_button.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        next_button.click(force=True)

        try:
            page.wait_for_function(
                """([oldFirst, oldCount]) => {
                    const els = document.querySelectorAll('%s');
                    const first = (els[0] && els[0].textContent || '').trim();
                    return first !== oldFirst || els.length !== oldCount;
                }"""
                % NAME_SELECTOR,
                arg=[old_first, old_count],
                timeout=15_000,
            )
        except Exception:
            break

        page.wait_for_timeout(1000)

    return list(products.values())


def _match_required_products(scraped_products: list[dict]) -> list[dict]:
    matched = []
    for required in REQUIRED_PRODUCTS:
        match = next(
            (p for p in scraped_products if _match_product(required["system_name"], p["name"])),
            None,
        )
        if match:
            matched.append(
                {
                    "dc_code": required["dc_code"],
                    "system_name": required["system_name"],
                    "keells_name": match["name"],
                    "category": match["category"],
                    "price": match["price"],
                }
            )
    return matched


def _find_an_admin(db: Session) -> User | None:
    return (
        db.query(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .filter(Role.code == "ADMIN", User.is_active.is_(True))
        .order_by(User.id)
        .first()
    )


def run_scrape(db: Session, admin: User | None = None, delivery_date: date | None = None) -> dict:
    """
    Launches a headless Chromium, scrapes both Keells category pages,
    matches against REQUIRED_PRODUCTS, and upserts a KEELLS reference
    price for every match — for `delivery_date`, or the current price
    window's delivery date if not given (same default used everywhere
    else reference prices are set). Raises KeellsScrapeError if nothing
    could be matched at all; individual unmatched/unparsable rows are
    just skipped and reported back, same as the Excel-import path.
    """
    from playwright.sync_api import sync_playwright  # imported lazily — only the scrape worker needs this

    admin = admin or _find_an_admin(db)
    if not admin:
        raise KeellsScrapeError("No active ADMIN account found to attribute this import to.")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            local_fruits = _scrape_category(page, LOCAL_FRUITS_URL, "Local Fruits", needs_view_all=False)
            fresh_vegetables = _scrape_category(page, FRESH_VEGETABLES_URL, "Fresh Vegetables", needs_view_all=True)
        finally:
            browser.close()

    all_scraped = local_fruits + fresh_vegetables
    matched = _match_required_products(all_scraped)
    if not matched:
        raise KeellsScrapeError(
            "Scraped the Keells site but matched zero known items — page layout may have changed."
        )

    products_by_code = {p.product_code: p for p in db.query(Product).all()}
    if delivery_date is None:
        delivery_date = pricing_service.get_price_window(db).delivery_date

    saved = 0
    skipped_no_price = 0
    unmatched: list[dict] = []
    for row in matched:
        price = _parse_price(row["price"])
        if price is None:
            skipped_no_price += 1
            continue
        product = products_by_code.get(row["dc_code"])
        if not product:
            unmatched.append({"dc_code": row["dc_code"], "system_name": row["system_name"]})
            continue
        pricing_service.set_reference_price(db, admin, product.id, delivery_date, price, SOURCE)
        saved += 1

    return {
        "delivery_date": delivery_date,
        "scraped": len(all_scraped),
        "matched": len(matched),
        "saved": saved,
        "skipped_no_price": skipped_no_price,
        "unmatched": unmatched,
    }
