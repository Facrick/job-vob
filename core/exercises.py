"""exercises.py — банк практических заданий для режима «Упражнения» учебника.

Гибрид: статичный seed-банк (bundled, только чтение) + пользовательский банк
(writable), куда складываются сгенерированные ИИ задания, чтобы переиспользовать
их позже без повторного обращения к модели. Ключ — текст темы (question).

Формат одного задания:
    {"task": "<условие>", "reference": "<скрытый эталон>", "rubric": "<критерии>"}
reference и rubric пользователю не показываются — по ним ИИ оценивает ответ.
"""
from __future__ import annotations

import json
import logging

from core.paths import resource_path, user_path


class ExerciseBank:
    def __init__(self) -> None:
        self._seed = self._load(resource_path("data/exercises.json"))
        self._custom_path = user_path("data/exercises_custom.json")
        self._custom = self._load(self._custom_path)

    @staticmethod
    def _load(path) -> dict[str, list[dict]]:
        try:
            if path and path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception as e:  # noqa: BLE001
            logging.error(f"[Exercises] Не удалось загрузить {path}: {e}")
        return {}

    def get_for_topic(self, question: str) -> list[dict]:
        """Все задания по теме: сначала seed, затем пользовательские/сгенерированные."""
        out = list(self._seed.get(question, []))
        out.extend(self._custom.get(question, []))
        return [e for e in out if isinstance(e, dict) and e.get("task")]

    def add(self, question: str, exercise: dict) -> None:
        """Сохраняет задание в пользовательский банк (накопление гибрида)."""
        if not (exercise and exercise.get("task")):
            return
        self._custom.setdefault(question, []).append(exercise)
        try:
            self._custom_path.write_text(
                json.dumps(self._custom, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:  # noqa: BLE001
            logging.error(f"[Exercises] Не удалось сохранить банк: {e}")
