import logging
import sys

from app.core.config import settings


def configure_logging() -> None:
    """
    Central logging setup. Never log passwords, tokens, or other secrets.
    """
    level = logging.DEBUG if settings.APP_ENV == "development" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Quiet noisy third-party loggers
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
