# Hosting on a VPS

This deploys the exact same app you run locally, with three production
changes: the database is no longer reachable from the internet, the
frontend is a real static build (not the dev server), and Caddy sits in
front of everything to get you free, automatic HTTPS.

Everything below was tested in a sandbox (backend, the built frontend
served by nginx, and Caddy's reverse-proxy routing all verified working
together) — the one thing that genuinely can't be tested without a real
server and a real domain is the actual Let's Encrypt certificate
issuance, since that requires the public internet to reach your server.

## 1. Get a server

Any of these work fine for this app's size — pick based on price/location:
- DigitalOcean, Hetzner, Linode/Akamai — all around $6/month for a small
  droplet (1 vCPU, 1-2GB RAM is plenty to start).
- Choose **Ubuntu 24.04 LTS** as the OS image.
- Note the server's public IP address once it's created.

## 2. Point a domain at it

You need a real domain name — Caddy's automatic HTTPS won't work with a
bare IP address. In your domain registrar's DNS settings, add:

```
Type: A
Name: @  (or a subdomain like "app")
Value: <your server's IP address>
```

DNS changes can take a few minutes to a few hours to propagate. You can
check with `nslookup yourdomain.com` from your own computer.

## 3. Install Docker on the server

SSH into the server (`ssh root@<server-ip>`), then:

```bash
curl -fsSL https://get.docker.com | sh
```

That installs Docker and the Compose plugin in one step.

## 4. Get the project onto the server

Either `git clone` your repository, or upload the zip and unzip it:

```bash
scp spar-project-updated.zip root@<server-ip>:/root/
ssh root@<server-ip>
cd /root && unzip spar-project-updated.zip && cd spar-project
```

## 5. Configure production settings

```bash
cp .env.example .env.production
nano .env.production
```

Fill in real values:
- `SECRET_KEY` — generate one: `openssl rand -hex 32`
- `CORS_ORIGINS` — `["https://yourdomain.com"]`
- Leave `DATABASE_URL` as-is; `docker-compose.prod.yml` overrides it automatically.
- Fill in `SMTP_*` if you want "Send to Master Data" to work.

Then add two more variables `docker-compose.prod.yml` needs, either in
`.env.production` or exported before running compose:

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env.production
echo "PUBLIC_URL=https://yourdomain.com" >> .env.production
```

## 6. Edit the Caddyfile

Open `Caddyfile` and replace `yourdomain.com` with your actual domain —
this is the only edit it needs.

## 7. Build and start everything

```bash
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend python3 scripts/seed_master_data.py
docker compose -f docker-compose.prod.yml exec backend python3 scripts/seed_users.py
```

Caddy will automatically request and install an HTTPS certificate the
first time it sees real traffic for your domain — no extra step needed.

## 8. Check it worked

Visit `https://yourdomain.com` — you should see the login page, served
over a real HTTPS connection with a valid certificate.

## Updating later

```bash
cd /root/spar-project
# replace files with the new version, then:
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## Backing up the database

A `db-backup` service runs automatically as part of `docker compose -f
docker-compose.prod.yml up -d` — no cron job to set up or remember. It
dumps the database on startup and then once a day after that (gzipped,
timestamped), keeping the last 14 days by default in the `db_backups`
Docker volume. Both numbers are configurable in `.env.production`:

```bash
BACKUP_RETENTION_DAYS=14
BACKUP_INTERVAL_SECONDS=86400
```

Check it's actually producing dumps:

```bash
docker compose -f docker-compose.prod.yml exec db-backup ls -lh /backups
```

**This alone does not protect against losing the whole server** — the
dumps live in a Docker volume on the same machine as the database. Copy
them off-server periodically too, e.g.:

```bash
docker compose -f docker-compose.prod.yml exec db-backup sh -c "cat /backups/\$(ls -t /backups | head -1)" > latest-backup.sql.gz
scp latest-backup.sql.gz you@your-other-machine:/somewhere/safe/
```

### Restoring from a backup

```bash
# copy the dump into the db container, then restore it
docker compose -f docker-compose.prod.yml cp latest-backup.sql.gz db:/tmp/restore.sql.gz
docker compose -f docker-compose.prod.yml exec db sh -c "gunzip -c /tmp/restore.sql.gz | psql -U spar_user spar_procurement"
```

Restoring overwrites existing rows with the same primary keys — only do
this against a database you intend to replace (e.g. after data loss),
not casually against a live one.
