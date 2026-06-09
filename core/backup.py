"""Автоматическое резервное копирование БД при запуске приложения.

Логика:
  • Создаёт backup_YYYYMMDD.db рядом с основной БД.
  • Одна копия в день — если файл уже есть, пропускает (не перезаписывает).
  • Хранит не более MAX_BACKUPS последних копий, старые удаляет.
  • Любая ошибка логируется, но НЕ прерывает запуск приложения.
"""
from __future__ import annotations

import logging
import shutil
from datetime import date
from pathlib import Path

MAX_BACKUPS = 7  # сколько ежедневных копий держать


def backup_database(db_path: str | Path) -> Path | None:
    """Создаёт дневную резервную копию БД.

    Возвращает путь к файлу копии (новой или уже существующей),
    либо None если исходная БД не существует или произошла ошибка.
    """
    src = Path(db_path)
    if not src.exists():
        return None  # БД ещё не создавалась — нечего копировать

    backup_dir = src.parent / "backups"
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logging.warning(f"[Backup] Не удалось создать папку резервных копий: {e}")
        return None

    today = date.today().strftime("%Y%m%d")
    dest = backup_dir / f"backup_{today}.db"

    if dest.exists():
        # Копия за сегодня уже есть — не трогаем
        logging.debug(f"[Backup] Копия за сегодня уже существует: {dest.name}")
        return dest

    try:
        shutil.copy2(src, dest)
        logging.info(f"[Backup] Резервная копия создана: {dest.name}")
        _cleanup_old_backups(backup_dir)
        return dest
    except Exception as e:
        logging.warning(f"[Backup] Не удалось создать резервную копию: {e}")
        return None


def _cleanup_old_backups(backup_dir: Path) -> None:
    """Удаляет старые резервные копии, оставляя MAX_BACKUPS последних."""
    backups = sorted(backup_dir.glob("backup_*.db"))
    excess = backups[: max(0, len(backups) - MAX_BACKUPS)]
    for old in excess:
        try:
            old.unlink()
            logging.info(f"[Backup] Удалена старая копия: {old.name}")
        except Exception as e:
            logging.warning(f"[Backup] Не удалось удалить {old.name}: {e}")
