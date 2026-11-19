#!/bin/sh
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"
PGHOST="${PGHOST:-db}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-${POSTGRES_USER:-agent}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-sports_agent}}"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
FILENAME="${BACKUP_DIR}/${PGDATABASE}_${TIMESTAMP}.sql.gz"

echo "[$(date -Iseconds)] [BACKUP] Starting PostgreSQL dump for database '${PGDATABASE}' from host '${PGHOST}:${PGPORT}'..."

# Perform compressed pg_dump
if pg_dump -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" --clean --if-exists --no-owner --no-privileges | gzip > "${FILENAME}"; then
    SIZE=$(du -h "${FILENAME}" | cut -f1)
    echo "[$(date -Iseconds)] [BACKUP] Successfully created backup: ${FILENAME} (${SIZE})"
else
    echo "[$(date -Iseconds)] [BACKUP] ERROR: pg_dump failed!" >&2
    rm -f "${FILENAME}"
    exit 1
fi

# Retention policy: SPEC v1.3 §12 requires 14 days retention
echo "[$(date -Iseconds)] [BACKUP] Purging backups older than ${RETENTION_DAYS} days in ${BACKUP_DIR}..."
find "${BACKUP_DIR}" -name "${PGDATABASE}_*.sql.gz" -type f -mtime +"${RETENTION_DAYS}" -exec echo "[PURGE] Removing old backup: {}" \; -exec rm -f {} +

echo "[$(date -Iseconds)] [BACKUP] Backup and rotation cycle finished successfully."
