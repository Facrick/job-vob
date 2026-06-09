"""Тесты резервного копирования БД."""
import shutil
from datetime import date
from pathlib import Path

import pytest

from core.backup import MAX_BACKUPS, backup_database, _cleanup_old_backups


@pytest.fixture()
def tmp_db(tmp_path):
    """Создаёт временную «БД» с данными."""
    db = tmp_path / "app.db"
    db.write_bytes(b"fake-db-content")
    return db


def test_creates_backup(tmp_db):
    result = backup_database(tmp_db)
    assert result is not None
    assert result.exists()
    today = date.today().strftime("%Y%m%d")
    assert result.name == f"backup_{today}.db"
    assert result.read_bytes() == b"fake-db-content"


def test_backup_in_backups_subdir(tmp_db):
    result = backup_database(tmp_db)
    assert result.parent.name == "backups"


def test_no_duplicate_backup_same_day(tmp_db):
    first = backup_database(tmp_db)
    first.write_bytes(b"original")
    second = backup_database(tmp_db)
    # Второй вызов не должен перезаписать первый
    assert second == first
    assert second.read_bytes() == b"original"


def test_missing_db_returns_none(tmp_path):
    result = backup_database(tmp_path / "nonexistent.db")
    assert result is None


def test_cleanup_keeps_max_backups(tmp_path):
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    # Создаём MAX_BACKUPS + 3 старых файла
    for i in range(MAX_BACKUPS + 3):
        (backup_dir / f"backup_2025010{i:01d}.db").write_bytes(b"x")

    _cleanup_old_backups(backup_dir)
    remaining = sorted(backup_dir.glob("backup_*.db"))
    assert len(remaining) == MAX_BACKUPS
