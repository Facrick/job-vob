"""Единая точка разрешения путей: dev-запуск и PyInstaller-сборка.

Разделяем два вида ресурсов:
  • bundled (только чтение) — учебник, ассеты. В собранном .exe лежат во
    временной папке распаковки `sys._MEIPASS`.
  • user-data (чтение/запись) — БД, логи, письма, настройки. Их нельзя писать
    в `_MEIPASS` (read-only/временная), поэтому держим рядом с .exe / проектом.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Корень проекта (на уровень выше core/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _meipass() -> Path | None:
    """Папка распаковки PyInstaller, если приложение «заморожено»."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else None


def is_frozen() -> bool:
    return getattr(sys, "frozen", False) is True


def resource_path(relative: str) -> Path:
    """Путь к bundled-ресурсу только для чтения (учебник, ассеты).

    В dev — относительно корня проекта; в сборке — из `_MEIPASS`.
    """
    base = _meipass() or PROJECT_ROOT
    return base / relative


def user_data_dir() -> Path:
    """Каталог для записываемых данных (БД, логи, письма, настройки).

    • заморожено  → рядом с исполняемым файлом (../<exe>/data рядом);
    • dev         → корень проекта.
    """
    base = Path(sys.executable).resolve().parent if is_frozen() else PROJECT_ROOT
    return base


def user_path(relative: str) -> Path:
    """Путь к записываемому файлу/папке; создаёт родительский каталог."""
    p = user_data_dir() / relative
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
