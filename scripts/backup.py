"""PostgreSQL backup and retention utility per SPEC v1.3 §12.

Creates compressed pg_dump archives and purges backups older than retention days (default 14).
"""
import argparse
import gzip
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
logger = logging.getLogger("backup")


def run_backup(backup_dir: Path, retention_days: int = 14) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    db_name = os.environ.get("PGDATABASE") or os.environ.get("POSTGRES_DB") or "sports_agent"
    db_user = os.environ.get("PGUSER") or os.environ.get("POSTGRES_USER") or "agent"
    db_host = os.environ.get("PGHOST", "db")
    db_port = os.environ.get("PGPORT", "5432")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    target_path = backup_dir / f"{db_name}_{timestamp}.sql.gz"

    cmd = [
        "pg_dump",
        "-h", db_host,
        "-p", db_port,
        "-U", db_user,
        "-d", db_name,
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
    ]

    logger.info("Executing pg_dump for %s from %s:%s...", db_name, db_host, db_port)
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        with gzip.open(target_path, "wb") as gz_out:
            if proc.stdout is not None:
                while chunk := proc.stdout.read(65536):
                    gz_out.write(chunk)
        stderr_output = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
        retcode = proc.wait()
        if retcode != 0:
            if target_path.exists():
                target_path.unlink()
            raise RuntimeError(f"pg_dump exited with code {retcode}: {stderr_output}")

        size_kb = target_path.stat().st_size / 1024
        logger.info("Backup successfully created: %s (%.1f KB)", target_path, size_kb)
    except Exception as exc:
        if target_path.exists():
            target_path.unlink()
        logger.error("Failed to create backup: %s", exc)
        raise

    prune_old_backups(backup_dir, db_name, retention_days)
    return target_path


def prune_old_backups(backup_dir: Path, db_name: str, retention_days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    removed_count = 0
    pattern = f"{db_name}_*.sql.gz"

    for file_path in backup_dir.glob(pattern):
        if not file_path.is_file():
            continue
        mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            logger.info("Removing expired backup: %s (created %s)", file_path.name, mtime.isoformat())
            try:
                file_path.unlink()
                removed_count += 1
            except OSError as err:
                logger.warning("Could not delete %s: %s", file_path, err)

    logger.info("Rotation complete: purged %d expired backups (retention: %d days)", removed_count, retention_days)
    return removed_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PostgreSQL Backup & Rotation per SPEC v1.3 §12")
    parser.add_argument("--backup-dir", default=os.environ.get("BACKUP_DIR", "backups"), help="Directory for backup files")
    parser.add_argument("--retention-days", type=int, default=int(os.environ.get("BACKUP_RETENTION_DAYS", "14")), help="Retention period in days")
    args = parser.parse_args()

    try:
        run_backup(Path(args.backup_dir), args.retention_days)
    except Exception as e:
        logger.error("Backup failed: %s", e)
        sys.exit(1)
