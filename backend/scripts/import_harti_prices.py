"""
Runs harti_import_service.run_import once immediately, then once a day at
a fixed time (default 19:00 Asia/Colombo — after HARTI's own price
collection window, per the note printed on their bulletins), forever.
run_import itself checks five public price sources (HARTI, Dambulla DEC,
Keppetipola DEC, CBSL, GoviSaviya) — see that module for details.

Any failure (site down, format changed, network blip) is logged and the
loop keeps going and tries again at the next scheduled time — this must
never take the rest of the app down with it, since local market prices
are informational only and nothing else depends on them. A single
source failing doesn't count as a failure here; run_import only raises
if every source failed.

Usage:
    python -m scripts.import_harti_prices
"""
import logging
import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.database import SessionLocal
from app.services.harti_import_service import HartiImportError, run_import

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s harti_import: %(message)s")
logger = logging.getLogger("harti_import")

BUSINESS_TZ = ZoneInfo("Asia/Colombo")
RUN_HOUR = int(os.environ.get("HARTI_IMPORT_HOUR", "19"))


def _seconds_until_next_run(now: datetime) -> float:
    target = now.replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _run_once() -> None:
    db = SessionLocal()
    try:
        result = run_import(db)
        logger.info(
            "saved %s items into delivery_date %s — contributed=%s failures=%s",
            result["saved"], result["delivery_date"], result["contributed"], result["failures"],
        )
    except HartiImportError as e:
        logger.warning("import failed, will retry next scheduled run: %s", e)
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
