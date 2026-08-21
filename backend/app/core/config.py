"""
Central application configuration.
All values are read from environment variables (see /.env.example).
Never hard-code secrets here.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:5173", "http://localhost:8080"]


settings = Settings()
