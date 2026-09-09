# Hosting on Railway

An alternative to [HOSTING.md](HOSTING.md) (a VPS + Docker Compose + Caddy).
Railway runs each piece as its own service, gives you HTTPS and a public
domain per service automatically, and manages Postgres for you — so you
don't touch Caddy, `docker-compose.prod.yml`, or backups the same way.

You'll end up with 3 services in one Railway project: **Postgres**,
**backend**, and **frontend**.

## 1. Push the repo to GitHub

Railway deploys from a GitHub repo. If this project isn't on GitHub yet,
create a repo and push it there first.

## 2. Create the project and database

1. [railway.app](https://railway.app) → **New Project** → **Deploy from
   GitHub repo** → select this repo.
2. Railway will try to auto-deploy a service from the repo root — delete
   that first service, since this repo needs three separate services
   each pointed at a subdirectory (below), not one at the root.
3. **+ New** → **Database** → **Add PostgreSQL**. Railway provisions it
   and exposes `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`
   as variables you can reference from other services (step 3).

## 3. Backend service

**+ New** → **GitHub Repo** → this repo again.

- **Settings → Source → Root Directory**: `backend`
- **Settings → Build**: leave as-is — Railway detects `backend/Dockerfile`
  automatically. It already runs `alembic upgrade head` before starting
  uvicorn (see the `CMD` in that file), so migrations run on every deploy.
- **Variables**, add each of these (same meaning as `backend/.env.example`
  — copy real values from your own `backend/.env` where you have them):
  - `APP_ENV=production`
  - `DATABASE_URL` — reference the Postgres service instead of typing a
    value: click "New Variable" → "Add Reference", or paste this and
    adjust the service name if yours isn't called `Postgres`:
    ```
    postgresql+psycopg2://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
    ```
    (Railway's own `DATABASE_URL` reference uses `postgres://`, which
    SQLAlchemy here needs as `postgresql+psycopg2://` instead — that's
    why this is built manually rather than referenced directly.)
  - `SECRET_KEY` — generate one: `openssl rand -hex 32`
  - `CORS_ORIGINS=["https://REPLACE-ME"]` — the frontend's URL. You won't
    know this until step 4 generates a domain; come back and fill it in
    then, and redeploy.
  - `BRANCH_ORDER_DEADLINE=14:00`, `SUPPLIER_PRICE_DEADLINE=12:00` (or
    your real values)
  - `SMTP_*` — fill in if you want "Send to Master Data" to send email;
    otherwise leave blank, same as local dev.
  - `POS_API_BASE_URL`, `POS_API_USERNAME`, `POS_API_PASSWORD` — fill in
    if you want the branch order page's "Stock in Hand" column.
- **Settings → Networking → Generate Domain**: set the target port to
  `8000` (the port `backend/Dockerfile` exposes).

Once it deploys, run the one-time seed scripts (real data goes in via the
app itself after this — these just create the initial branches, products,
and admin/branch/supplier logins):

```bash
railway run --service backend python3 scripts/seed_master_data.py
railway run --service backend python3 scripts/seed_users.py
```

(Needs the [Railway CLI](https://docs.railway.com/guides/cli), logged in
and linked to this project: `railway login`, then `railway link`.)

## 4. Frontend service

**+ New** → **GitHub Repo** → this repo again.

- **Settings → Source → Root Directory**: `frontend`
- **Settings → Build → Dockerfile Path**: `Dockerfile.railway` — a
  Railway-specific variant of `Dockerfile.prod` (see the comment at the
  top of that file for why it can't just reuse `Dockerfile.prod` as-is:
  Vite needs `VITE_API_BASE_URL` baked in at build time, and on the VPS
  that comes from a local `frontend/.env.production` file that has no
  equivalent when Railway builds straight from this repo).
- **Variables**:
  - `VITE_API_BASE_URL` — the backend's Railway URL from step 3, e.g.
    `https://backend-production-xxxx.up.railway.app`. Railway passes
    service variables to `Dockerfile.railway`'s matching `ARG` during the
    build automatically — nothing else to configure.
- **Settings → Networking → Generate Domain**: set the target port to
  `80` (nginx, same as `Dockerfile.prod`).

## 5. Close the loop

Now that both services have real domains:

- Backend → Variables → set `CORS_ORIGINS` to the frontend's actual
  domain, e.g. `["https://frontend-production-xxxx.up.railway.app"]`,
  then redeploy.
- If `VITE_API_BASE_URL` was a placeholder in step 4, set it to the
  backend's actual domain and redeploy the frontend (Vite bakes it in at
  build time, so this needs a rebuild, not just a restart).

Visit the frontend's domain — you should see the login page.

## 6. Custom domain (optional)

Each service's **Settings → Networking → Custom Domain** walks you
through adding a CNAME at your DNS provider. Railway issues the HTTPS
certificate automatically once DNS resolves. If you do this, update
`CORS_ORIGINS` and `VITE_API_BASE_URL` to the custom domains instead of
the `*.up.railway.app` ones, and redeploy both services.

## What's different from the VPS setup

- **No Caddy.** Railway terminates HTTPS and reverse-proxies to each
  service itself — the `Caddyfile` and the `caddy` block in
  `docker-compose.prod.yml` are VPS-only and don't apply here.
- **No `autoheal` service.** Railway restarts unhealthy deploys itself.
- **No `db-backup` service.** Railway's own Postgres doesn't run the
  `docker/backup_db.sh` script from this repo. On paid Railway plans,
  Postgres has built-in automated backups (Database → Backups in the
  dashboard) — turn that on. Otherwise, back up manually with:
  ```bash
  railway run --service Postgres pg_dump -Fc "$DATABASE_URL" > backup.dump
  ```
- **`harti-price-import`** (the daily local-market-price import) isn't
  deployed by the steps above — it's optional and informational-only. To
  add it: **+ New** → **GitHub Repo** → this repo, **Root Directory**:
  `backend`, same `DATABASE_URL`/`APP_ENV` variables as the backend
  service, and **Settings → Deploy → Custom Start Command**:
  `python -m scripts.import_harti_prices`. No public domain needed for
  this one.

## Updating later

Push to the branch Railway is watching (`main` by default) — each
service with `backend` or `frontend` as its root directory redeploys on
every push automatically, migrations included (the backend's `CMD` runs
`alembic upgrade head` before starting).
