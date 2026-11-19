from datetime import datetime, timedelta, timezone
from pathlib import Path
import os

from scripts.backup import prune_old_backups


def test_prune_old_backups(tmp_path: Path):
    db_name = "test_db"
    now = datetime.now(timezone.utc)

    # 1. Recent backup (2 days old)
    recent_file = tmp_path / f"{db_name}_20261118_120000.sql.gz"
    recent_file.write_bytes(b"dummy")
    two_days_ago = (now - timedelta(days=2)).timestamp()
    os.utime(recent_file, (two_days_ago, two_days_ago))

    # 2. Old backup (16 days old) - should be deleted (retention is 14 days)
    old_file = tmp_path / f"{db_name}_20261101_120000.sql.gz"
    old_file.write_bytes(b"dummy")
    sixteen_days_ago = (now - timedelta(days=16)).timestamp()
    os.utime(old_file, (sixteen_days_ago, sixteen_days_ago))

    # 3. Another db backup - should not be touched
    other_file = tmp_path / "other_db_20261101_120000.sql.gz"
    other_file.write_bytes(b"dummy")
    os.utime(other_file, (sixteen_days_ago, sixteen_days_ago))

    removed = prune_old_backups(tmp_path, db_name, retention_days=14)

    assert removed == 1
    assert recent_file.exists()
    assert not old_file.exists()
    assert other_file.exists()
