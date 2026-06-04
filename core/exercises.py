"""exercises.py — банк практических заданий для режима «Упражнения» учебника.

Гибрид: статичный seed-банк (bundled, только чтение) + пользовательский банк
(writable), куда складываются сгенерированные ИИ задания, чтобы переиспользовать
их позже без повторного обращения к модели. Ключ — текст темы (question).

Формат одного задания:
    {"task": "<условие>", "reference": "<скрытый эталон>", "rubric": "<критерии>"}
reference и rubric пользователю не показываются — по ним ИИ оценивает ответ.

Прогресс выполнения хранится отдельно (exercises_progress.json): по каждой теме
лучший балл, число попыток и флаг «зачтено».
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from core.paths import resource_path, user_path

# Порог «зачтено» (совпадает с rubric в промпте оценки).
PASS_SCORE = 70


class ExerciseBank:
    def __init__(
        self,
        seed_path: str | Path | None = None,
        custom_path: str | Path | None = None,
        progress_path: str | Path | None = None,
    ) -> None:
        # Явные пути используются в тестах; иначе — штатные расположения.
        self._seed = self._load(
            Path(seed_path) if seed_path else resource_path("data/exercises.json")
        )
        self._custom_path = (
            Path(custom_path) if custom_path
            else user_path("data/exercises_custom.json")
        )
        self._custom = self._load(self._custom_path)
        self._progress_path = (
            Path(progress_path) if progress_path
            else user_path("data/exercises_progress.json")
        )
        self._progress = self._load(self._progress_path)

    @staticmethod
    def _load(path) -> dict:
        try:
            if path and path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return data
        except Exception as e:  # noqa: BLE001
            logging.error(f"[Exercises] Не удалось загрузить {path}: {e}")
        return {}

    @staticmethod
    def _save(path: Path, data: dict) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception as e:  # noqa: BLE001
            logging.error(f"[Exercises] Не удалось сохранить {path}: {e}")

    # ── Банк заданий ──────────────────────────────────────────────────
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
        self._save(self._custom_path, self._custom)

    # ── Прогресс ──────────────────────────────────────────────────────
    def record_result(
        self, question: str, score: int, verdict: str = ""
    ) -> dict:
        """Фиксирует попытку: обновляет лучший балл, счётчик и флаг «зачтено»."""
        if not question:
            return {}
        score = max(0, min(100, int(score)))
        prev = self._progress.get(question, {})
        entry = {
            "best_score": max(int(prev.get("best_score", 0)), score),
            "attempts": int(prev.get("attempts", 0)) + 1,
            "passed": bool(prev.get("passed", False)) or score >= PASS_SCORE,
            "last_score": score,
            "last_verdict": verdict or prev.get("last_verdict", ""),
        }
        self._progress[question] = entry
        self._save(self._progress_path, self._progress)
        return entry

    def get_progress(self, question: str) -> dict | None:
        """Прогресс по теме или None, если ещё не решали."""
        return self._progress.get(question)

    def stats(self) -> tuple[int, int]:
        """(зачтено, попыток было по темам) — для сводного бейджа."""
        attempted = len(self._progress)
        passed = sum(1 for p in self._progress.values() if p.get("passed"))
        return passed, attempted
