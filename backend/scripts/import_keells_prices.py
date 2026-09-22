"""
Runs keells_scrape_service.run_scrape once immediately, then once a day at
a fixed time (default 07:00 Asia/Colombo, ahead of the admin's typical
work day), forever. This is the automated replacement for running the
standalone scraper.js by hand and uploading its Excel output — see
keells_scrape_service.py for the scraping/matching logic itself, ported
from that reference script.

Any failure (site down, layout changed, network blip) is logged and the
loop keeps going and tries again at the next scheduled time — this must
never take the rest of the app down with it. Admin can also trigger an
immediate run from the Keells Price tab (POST /pricing/reference/keells-sync)
without waiting for this schedule.

Usage:
    python -m scripts.import_keells_prices
"""
import logging
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.database import SessionLocal
from app.services.keells_scrape_service import KeellsScrapeError, run_scrape

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s keells_import: %(message)s")
logger = logging.getLogger("keells_import")

BUSINESS_TZ = ZoneInfo("Asia/Colombo")
RUN_HOUR = int(os.environ.get("KEELLS_IMPORT_HOUR", "7"))


def _seconds_until_next_run(now: datetime) -> float:
    target = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _run_once() -> None:
    db = SessionLocal()
    try:
        result = run_scrape(db)
        logger.info(
            "saved %s/%s matched items (scraped %s) into delivery_date %s — unmatched=%s",
            result["saved"], result["matched"], result["scraped"], result["delivery_date"], result["unmatched"],
        )
    except KeellsScrapeError as e:
        logger.warning("scrape failed, will retry next scheduled run: %s", e)
    finally:
        db.close()


def main() -> None:
    logger.info("starting — daily run at %02d:00 Asia/Colombo", RUN_HOUR)
    _run_once()
    while True:
        sleep_seconds = _seconds_until_next_run(datetime.now(BUSINESS_TZ))
        logger.info("sleeping %.0fs until next run", sleep_seconds)
        time.sleep(sleep_seconds)
        _run_once()


if __name__ == "__main__":
    main()
