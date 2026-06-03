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
import re
from pathlib import Path

from core.paths import resource_path, user_path

# Раздел, куда складываются сгенерированные ИИ материалы.
AI_SECTION = "🤖 ИИ-материалы (на проверку)"

# Только реально «пустые» слова — QA-термины (тестирование, автоматизация) НЕ сюда.
_STOPWORDS = {
    "опыт", "работа", "работы", "работать", "знание", "знания", "умение", "умения",
    "навык", "навыки", "навыков", "уровень", "понимание", "желательно", "плюсом",
    "общие", "основные", "базовые", "хорошее", "глубокое", "будет", "требуется",
    "and", "the", "for", "with", "или", "для", "это", "как", "что",
}

# Синонимы/зонтичные термины → канонические слова, которые есть в учебнике.
_ALIASES = {
    "автотестирование": ["автоматизация"], "автотестирования": ["автоматизация"],
    "автотест": ["автоматизация"], "автотесты": ["автоматизация"],
    "автотестов": ["автоматизация"], "aqa": ["автоматизация"],
    "автоматизированное": ["автоматизация"],
    "субд": ["sql"], "ооп": ["ооп"], "oop": ["ооп"],
}


def _tokenize(text: str) -> list[str]:
    """Слова ≥3 символов; дефис/запятая режут (sql-запросы → sql, запросы),
    а / . + # остаются внутри тех-терминов (ci/cd, rest)."""
    return re.findall(r"[a-zа-яё0-9+#./]{3,}", (text or "").lower())


def _significant_tokens(text: str) -> list[str]:
    """Токены запроса: без стоп-слов, с раскрытием синонимов."""
    out: list[str] = []
    for t in _tokenize(text):
        if t in _STOPWORDS:
            continue
        out.extend(_ALIASES.get(t, [t]))
    return out


def _fuzzy_match(a: str, b: str, n: int = 5) -> bool:
    """Совпадение слов по ОБЩЕМУ ПРЕФИКСУ (корню), а не любому фрагменту.

    Так словоформы совпадают (тестирование/тестирования, автоматизация/
    автоматизировать → общий корень), а ложные совпадения по суффиксу
    исключены (автоматиз**ация** ≠ контейнер**изация**). Короткие слова (≤4) —
    только точное совпадение.
    """
    if min(len(a), len(b)) <= 4:
        return a == b
    i, m = 0, min(len(a), len(b))
    while i < m and a[i] == b[i]:
        i += 1
    return i >= n


class QAHandbook:
    def __init__(self, data_path: str | None = None, overlay_path: str | None = None,
                 prefs_path: str | None = None):
        self.data_path = self._resolve_path(data_path)
        # Записываемый overlay: ИИ-сгенерированные и отредактированные темы.
        # Базовый handbook.json в собранном .exe только для чтения, поэтому
        # пользовательский контент хранится отдельно и мержится поверх базы.
        self.overlay_path = Path(overlay_path) if overlay_path else user_path("data/handbook_custom.json")
        # Пользовательские настройки (избранное) — отдельный файл.
        self.prefs_path = Path(prefs_path) if prefs_path else user_path("data/handbook_prefs.json")
        self._base: dict[str, list[dict]] = self._load()
        self._overlay: dict[str, list[dict]] = self._load_overlay()
        self.sections: dict[str, list[dict]] = self._merge()
        prefs = self._load_prefs()
        self.favorites: set[str] = set(prefs.get("favorites", []))
        self.studied: set[str] = set(prefs.get("studied", []))

    # ── Настройки пользователя: избранное и прогресс («изучено») ──────
    def _load_prefs(self) -> dict:
        if not self.prefs_path.exists():
            return {}
        try:
            with open(self.prefs_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_prefs(self):
        try:
            self.prefs_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"favorites": sorted(self.favorites), "studied": sorted(self.studied)}
            with open(self.prefs_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"[Handbook] Не удалось сохранить настройки: {e}")

    @staticmethod
    def _toggle(coll: set[str], question: str) -> bool:
        if question in coll:
            coll.discard(question)
            return False
        coll.add(question)
        return True

    def is_favorite(self, question: str) -> bool:
        return question in self.favorites

    def toggle_favorite(self, question: str) -> bool:
        state = self._toggle(self.favorites, question)
        self._save_prefs()
        return state

    def is_studied(self, question: str) -> bool:
        return question in self.studied

    def toggle_studied(self, question: str) -> bool:
        state = self._toggle(self.studied, question)
        self._save_prefs()
        return state

    def progress(self) -> tuple[int, int]:
        """(изучено, всего тем) по всему учебнику."""
        total = sum(len(items) for items in self.sections.values())
        done = sum(1 for items in self.sections.values()
                   for it in items if it.get("question") in self.studied)
        return done, total

    def section_progress(self, section: str) -> tuple[int, int]:
        items = self.sections.get(section, [])
        done = sum(1 for it in items if it.get("question") in self.studied)
        return done, len(items)

    # ── Overlay (пользовательский/ИИ контент) ─────────────────────────
    def _load_overlay(self) -> dict[str, list[dict]]:
        if not self.overlay_path.exists():
            return {}
        try:
            with open(self.overlay_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"[Handbook] Не удалось прочитать overlay: {e}")
            return {}

    def _persist_overlay(self):
        try:
            self.overlay_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.overlay_path, "w", encoding="utf-8") as f:
                json.dump(self._overlay, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"[Handbook] Не удалось сохранить overlay: {e}")

    def _merge(self) -> dict[str, list[dict]]:
        """База + overlay: одноимённые вопросы заменяются, новые — добавляются."""
        merged: dict[str, list[dict]] = {k: list(v) for k, v in self._base.items()}
        for section, items in self._overlay.items():
            base_items = merged.setdefault(section, [])
            by_q = {it.get("question"): i for i, it in enumerate(base_items)}
            for it in items:
                q = it.get("question")
                if q in by_q:
                    base_items[by_q[q]] = it       # правка существующего
                else:
                    base_items.append(it)           # новый материал
        return merged

    def add_or_update_topic(self, section: str, question: str, answer: str,
                            ai: bool = False) -> None:
        """Добавляет/обновляет тему в overlay и пересобирает учебник."""
        item = {"question": question, "answer": answer, "source": "ai" if ai else "user"}
        items = self._overlay.setdefault(section, [])
        for i, it in enumerate(items):
            if it.get("question") == question:
                items[i] = item
                break
        else:
            items.append(item)
        self._persist_overlay()
        self.sections = self._merge()
        logging.info(f"[Handbook] Тема сохранена в overlay: «{question}» ({section})")

    def _resolve_path(self, data_path: str | None) -> Path | None:
        """Ищет handbook.json независимо от cwd и режима (dev/frozen).

        Единственный источник правды — data/handbook.json. В PyInstaller-сборке
        файл распаковывается в _MEIPASS и находится через resource_path().
        """
        candidates = []
        if data_path:
            candidates.append(Path(data_path))
        candidates.extend([
            resource_path("data/handbook.json"),  # dev: корень проекта; frozen: _MEIPASS
            resource_path("handbook.json"),        # запасной вариант в _MEIPASS
            Path("data/handbook.json"),            # относительно cwd
        ])

        for candidate in candidates:
            if candidate.exists():
                return candidate

        logging.error(
            "[Handbook] handbook.json не найден. Искал в: "
            + ", ".join(str(c) for c in candidates)
        )
        return None

    def _load(self) -> dict[str, list[dict]]:
        if self.data_path is None:
            return {}
        try:
            with open(self.data_path, encoding="utf-8") as f:
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

    def get_all_sections(self) -> dict[str, list[dict]]:
        return self.sections

    def find_topic(self, term: str) -> tuple | None:
        """Лучший подпункт учебника → (раздел, вопрос, ответ, source) или None.

        Сопоставление по ЗНАЧИМЫМ словам (без общих стоп-слов) и по ЦЕЛЫМ
        словам в тексте вопроса (а не подстроке). Если совпадений нет — None
        (вызывающий код предложит сгенерировать материал). source: "" (база/
        HTML), "ai"/"user" (overlay/Markdown) — для выбора способа рендера.
        """
        tokens = _significant_tokens(term)
        if not tokens:
            return None

        best, best_score = None, 0
        for section, items in self.sections.items():
            for it in items:
                q_tokens = _tokenize(it.get("question", ""))
                score = sum(
                    1 for t in tokens
                    if any(_fuzzy_match(t, qt) for qt in q_tokens)
                )
                if score > best_score:
                    best_score = score
                    best = (section, it.get("question", ""), it.get("answer", ""),
                            it.get("source", ""))
        return best if best_score >= 1 else None
