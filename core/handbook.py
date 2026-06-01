"""Справочник QA для учебника и mock-интервью.

Контент вынесен в data/handbook.json — раньше 701 строка HTML
была захардкожена прямо в этом файле. Теперь добавление вопросов
и перевод не требуют правки кода.

Файл ищется в нескольких местах, чтобы не зависеть от текущей
рабочей директории (частая причина "учебник не открывается").
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional


class QAHandbook:
    def __init__(self, data_path: Optional[str] = None):
        self.data_path = self._resolve_path(data_path)
        self.sections: Dict[str, List[dict]] = self._load()

    def _resolve_path(self, data_path: Optional[str]) -> Optional[Path]:
        """Ищет handbook.json в разумных местах независимо от cwd."""
        candidates = []
        if data_path:
            candidates.append(Path(data_path))

        # Папка проекта = на уровень выше core/
        project_root = Path(__file__).resolve().parent.parent
        candidates.extend([
            Path("data/handbook.json"),               # относительно cwd
            project_root / "data" / "handbook.json",  # относительно проекта
            Path(__file__).resolve().parent / "handbook.json",  # рядом с модулем
        ])

        for candidate in candidates:
            if candidate.exists():
                return candidate

        logging.error(
            "[Handbook] handbook.json не найден. Искал в: "
            + ", ".join(str(c) for c in candidates)
        )
        return None

    def _load(self) -> Dict[str, List[dict]]:
        if self.data_path is None:
            return {}
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                sections = json.load(f)
            logging.info(
                f"[Handbook] Загружено секций: {len(sections)} из {self.data_path}"
            )
            return sections
        except json.JSONDecodeError as e:
            logging.error(f"[Handbook] Ошибка парсинга JSON: {e}")
            return {}
        except Exception as e:
            logging.error(f"[Handbook] Не удалось прочитать справочник: {e}")
            return {}

    def get_all_sections(self) -> Dict[str, List[dict]]:
        return self.sections

    def get_topics(self) -> List[str]:
        """Список названий секций — используется как темы для mock-интервью."""
        return list(self.sections.keys())
