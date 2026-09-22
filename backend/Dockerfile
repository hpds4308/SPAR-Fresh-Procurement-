FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Headless Chromium + its OS deps — needed for the admin-triggered "Sync
# from Keells Now" button (POST /pricing/reference/keells-sync), which
# runs a real scrape from this same service. The scheduled daily import
# (scripts/import_keells_prices.py) runs in its own separate container
# (Dockerfile.keells-scrape) instead of here, but the on-demand trigger
# lives on the main API, so this image needs the browser too.
RUN playwright install --with-deps chromium

COPY . .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
