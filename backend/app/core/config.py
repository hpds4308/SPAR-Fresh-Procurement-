"""
Central application configuration.
All values are read from environment variables (see /.env.example).
Never hard-code secrets here.
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Values that ship in this repo / .env.example as placeholders. Anyone can read them,
# and a JWT only needs a user id to be forged once the signing key is known.
_PLACEHOLDER_SECRET_PREFIXES = ("changeme",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    APP_NAME: str = "SPAR Sri Lanka Procurement Platform"
    APP_ENV: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://spar_user:spar_password@db:5432/spar_procurement"

    # Auth / JWT
    SECRET_KEY: str = "changeme-generate-a-real-secret-in-.env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7

    # Business defaults (also stored in system_settings table, these are fallback defaults)
    BRANCH_ORDER_DEADLINE: str = "14:00"
    SUPPLIER_PRICE_DEADLINE: str = "12:00"

    # Email (used for e.g. "Send to Master Data" on the Master Data Sheet
    # page). Left blank by default — if SMTP_HOST isn't set, email-sending
    # endpoints return a clear error instead of trying and silently failing.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = ""
    SMTP_USE_TLS: bool = True

    # 24X7Retail / Dynamic Web POS integration (see the Web API Document
    # supplied by SPAR's POS vendor) — used for the branch order form's
    # stock-in-hand lookup. Left blank by default; if POS_API_BASE_URL
    # isn't set, the stock-in-hand lookup is skipped entirely rather than
    # trying and failing — it's a display enhancement, never a blocker
    # for placing an order.
    POS_API_BASE_URL: str = ""
    POS_API_USERNAME: str = ""
    POS_API_PASSWORD: str = ""

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8080"]

    @model_validator(mode="after")
    def _refuse_placeholder_secret_in_production(self) -> "Settings":
        """
        Fail fast at startup instead of quietly signing tokens with a publicly
        known key. Only the repo's own placeholder values are refused (not merely
        "short" keys), so a deployment that already uses its own key keeps booting.
        Generate one with:  openssl rand -hex 32
        """
        if self.APP_ENV == "production" and self.SECRET_KEY.strip().lower().startswith(_PLACEHOLDER_SECRET_PREFIXES):
            raise ValueError(
                "SECRET_KEY is still the placeholder value from .env.example. Set a real random SECRET_KEY "
                "(e.g. `openssl rand -hex 32`) before starting with APP_ENV=production."
            )
        return self


settings = Settings()
