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

# ── Мультитрек учебника (M20) ─────────────────────────────────────────────
# Учебник больше не привязан только к QA: помимо встроенного QA-контента
# поддерживаются направления Backend/Frontend/Data/DevOps. Их база может быть
# пустой — контент наполняется ИИ-генерацией и правками (overlay), как в M22.
DEFAULT_TRACK = "qa"
TRACKS: dict[str, str] = {
    "qa": "QA / Тестирование",
    "backend": "Backend",
    "frontend": "Frontend",
    "data": "Data / Аналитика",
    "devops": "DevOps",
}
# Персона для ИИ-генерации/квиза — задаёт направление сгенерированных материалов.
TRACK_PERSONAS: dict[str, str] = {
    "qa": "",  # дефолтный промпт уже QA-ориентирован
    "backend": "Backend-разработчик: серверная разработка, API, базы данных, "
               "архитектура, производительность",
    "frontend": "Frontend-разработчик: JavaScript/TypeScript, вёрстка, "
                "браузерные API, фреймворки (React/Vue/Angular), доступность",
    "data": "Data-инженер/аналитик: SQL, ETL/ELT, пайплайны данных, "
            "хранилища, визуализация и аналитика",
    "devops": "DevOps-инженер: CI/CD, контейнеризация, Kubernetes, облака, "
              "инфраструктура как код, мониторинг",
}

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
                 prefs_path: str | None = None, track: str | None = None):
        # Явные пути (используются в тестах) фиксируют QA-трек.
        self._data_path_override = data_path
        self._overlay_path_override = overlay_path
        self._prefs_path_override = prefs_path
        if track is None:
            track = DEFAULT_TRACK if (data_path or overlay_path or prefs_path) \
                else self._load_last_track()
        self.track: str = track if track in TRACKS else DEFAULT_TRACK
        self._apply_track()

    # ── Мультитрек ────────────────────────────────────────────────────
    def _track_state_path(self) -> Path:
        return user_path("data/handbook_track.json")

    def _load_last_track(self) -> str:
        try:
            p = self._track_state_path()
            if p.exists():
                with open(p, encoding="utf-8") as f:
                    t = json.load(f).get("track")
                if t in TRACKS:
                    return t
        except Exception:
            pass
        return DEFAULT_TRACK

    def _save_last_track(self):
        try:
            p = self._track_state_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"track": self.track}, f, ensure_ascii=False)
        except Exception as e:
            logging.error(f"[Handbook] Не удалось сохранить трек: {e}")

    def _resolve_optional(self, rel: str) -> Path | None:
        """Тихо ищет базовый файл трека; None — если базы нет (контент из ИИ)."""
        for c in (resource_path(rel), Path(rel)):
            if c and c.exists():
                return c
        return None

    def _track_paths(self, track: str) -> tuple[Path | None, Path, Path]:
        """Пути (база, overlay, prefs) для трека. QA сохраняет старые имена."""
        if track == DEFAULT_TRACK:
            base = self._resolve_path(self._data_path_override)
            overlay = (Path(self._overlay_path_override) if self._overlay_path_override
                       else user_path("data/handbook_custom.json"))
            prefs = (Path(self._prefs_path_override) if self._prefs_path_override
                     else user_path("data/handbook_prefs.json"))
        else:
            base = self._resolve_optional(f"data/handbook_{track}.json")
            overlay = user_path(f"data/handbook_custom_{track}.json")
            prefs = user_path(f"data/handbook_prefs_{track}.json")
        return base, overlay, prefs

    def _apply_track(self):
        """Загружает базу/overlay/prefs текущего трека и пересобирает учебник."""
        self.data_path, self.overlay_path, self.prefs_path = self._track_paths(self.track)
        self._base = self._load()
        self._overlay = self._load_overlay()
        self.sections = self._merge()
        prefs = self._load_prefs()
        self.favorites = set(prefs.get("favorites", []))
        self.studied = set(prefs.get("studied", []))

    def set_track(self, track: str):
        """Переключает направление учебника (контент, прогресс, избранное)."""
        if track not in TRACKS or track == self.track:
            return
        self.track = track
        self._save_last_track()
        self._apply_track()

    @property
    def persona(self) -> str:
        """Персона текущего трека для ИИ-генерации/квиза («» для QA)."""
        return TRACK_PERSONAS.get(self.track, "")

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
        term_low = (term or "").strip().lower()

        best, best_key = None, None
        for section, items in self.sections.items():
            for it in items:
                q = it.get("question", "")
                q_tokens = _tokenize(q)
                matched = sum(
                    1 for t in tokens if any(_fuzzy_match(t, qt) for qt in q_tokens)
                )
                if matched == 0:
                    continue
                coverage = matched / len(tokens)
                # Точное вхождение всей искомой фразы в вопрос — сильнейший сигнал
                # (например, «Stream API» целиком есть в заголовке темы).
                exact_phrase = bool(term_low) and term_low in q.lower()
                # Сортировочный ключ: точная фраза → покрытие → число совпадений.
                # При полном равенстве остаётся первый встреченный (порядок разделов).
                key = (exact_phrase, coverage, matched)
                if best_key is None or key > best_key:
                    best_key = key
                    best = (section, q, it.get("answer", ""), it.get("source", ""))

        if best is None:
            return None
        exact_phrase, coverage, matched = best_key
        # Отсекаем слабые совпадения: одиночное общее слово на длинной фразе
        # (низкое покрытие, без точного вхождения) — это «не туда».
        if exact_phrase or coverage >= 0.5 or matched >= 2:
            return best
        return None
