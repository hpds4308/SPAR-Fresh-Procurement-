#!/bin/sh
# Runs inside the db-backup service (docker-compose.prod.yml), reusing the
# postgres:16 image purely for its pg_dump binary — no separate image to
# build or host cron job to remember to set up. Dumps immediately on
# startup, then repeats on BACKUP_INTERVAL_SECONDS, deleting dumps older
# than BACKUP_RETENTION_DAYS so the volume doesn't grow forever.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
INTERVAL_SECONDS="${BACKUP_INTERVAL_SECONDS:-86400}"

mkdir -p "$BACKUP_DIR"
echo "backup_db: dumping every ${INTERVAL_SECONDS}s, keeping ${RETENTION_DAYS} days, writing to ${BACKUP_DIR}"

while true; do
  timestamp=$(date +%Y%m%d-%H%M%S)
  dest="$BACKUP_DIR/${POSTGRES_DB}-${timestamp}.sql.gz"

  if PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h db -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "${dest}.tmp"; then
    mv "${dest}.tmp" "$dest"
    echo "backup_db: wrote $dest"
  else
    echo "backup_db: pg_dump FAILED at $timestamp" >&2
    rm -f "${dest}.tmp"
  fi

  find "$BACKUP_DIR" -name "${POSTGRES_DB}-*.sql.gz" -mtime "+${RETENTION_DAYS}" -delete

  sleep "$INTERVAL_SECONDS"
done
