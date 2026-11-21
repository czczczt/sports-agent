#!/bin/sh
set -eu

if [ $# -lt 1 ]; then
    echo "Usage: $0 <path_to_backup.sql.gz | path_to_backup.sql>"
    exit 1
fi

BACKUP_FILE="$1"
PGHOST="${PGHOST:-db}"
PGPORT="${PGPORT:-5432}"
PGUSER="${PGUSER:-${POSTGRES_USER:-agent}}"
PGDATABASE="${PGDATABASE:-${POSTGRES_DB:-sports_agent}}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: Backup file '${BACKUP_FILE}' not found!" >&2
    exit 1
fi

echo "[$(date -Iseconds)] [RESTORE] Restoring database '${PGDATABASE}' on '${PGHOST}:${PGPORT}' from '${BACKUP_FILE}'..."

case "${BACKUP_FILE}" in
    *.gz)
        gzip -dc "${BACKUP_FILE}" | psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}"
        ;;
    *)
        psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" < "${BACKUP_FILE}"
        ;;
esac

echo "[$(date -Iseconds)] [RESTORE] Database restored successfully."
