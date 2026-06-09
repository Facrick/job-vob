"""Словарь синонимов должностей для расширенного поиска вакансий.

expand_query(text) возвращает [text] + подходящие синонимы из словаря.
Поиск по ключу нечувствителен к регистру и обрезает пробелы.
"""
from __future__ import annotations

# Ключ — нормализованное (lower) название роли.
# Значения — синонимы, которые добавятся к основному запросу.
_SYNONYMS: dict[str, list[str]] = {
    # ── QA / тестирование ────────────────────────────────────────────────
    "qa engineer": [
        "тестировщик ПО",
        "инженер по тестированию",
        "AQA инженер",
        "SDET",
    ],
    "qa": [
        "тестировщик",
        "QA engineer",
        "инженер по тестированию",
        "AQA",
    ],
    "тестировщик": [
        "QA engineer",
        "QA инженер",
        "инженер по тестированию",
        "AQA",
    ],
    "тестировщик по": [
        "QA engineer",
        "инженер по тестированию",
        "SDET",
    ],
    "инженер по тестированию": [
        "QA engineer",
        "тестировщик ПО",
        "AQA инженер",
        "SDET",
    ],
    "aqa": [
        "automation QA engineer",
        "автоматизатор тестирования",
        "SDET",
        "test automation engineer",
    ],
    "automation qa": [
        "AQA инженер",
        "автоматизатор тестирования",
        "SDET",
        "test automation engineer",
    ],
    "sdet": [
        "AQA",
        "automation QA engineer",
        "инженер по автоматизации тестирования",
    ],
    "автоматизатор тестирования": [
        "AQA engineer",
        "SDET",
        "test automation engineer",
    ],
    # ── Разработка ───────────────────────────────────────────────────────
    "python developer": [
        "python разработчик",
        "backend developer python",
        "software engineer python",
    ],
    "python разработчик": [
        "python developer",
        "backend developer python",
        "разработчик backend python",
    ],
    "frontend developer": [
        "frontend разработчик",
        "фронтенд разработчик",
        "react developer",
        "vue developer",
    ],
    "backend developer": [
        "backend разработчик",
        "бэкенд разработчик",
        "server-side developer",
    ],
    # ── DevOps / Infra ────────────────────────────────────────────────────
    "devops engineer": [
        "DevOps инженер",
        "инженер DevOps",
        "SRE engineer",
        "platform engineer",
    ],
    "devops": [
        "DevOps engineer",
        "инженер DevOps",
        "SRE",
    ],
}


def expand_query(text: str, max_synonyms: int = 3) -> list[str]:
    """Возвращает [text] + синонимы (не более max_synonyms).

    Если подходящего ключа в словаре нет — возвращает [text].

    >>> expand_query("QA Engineer")
    ['QA Engineer', 'тестировщик ПО', 'инженер по тестированию', 'AQA инженер']
    >>> expand_query("менеджер продукта")
    ['менеджер продукта']
    """
    key = text.strip().lower()
    synonyms = _SYNONYMS.get(key, [])
    return [text] + synonyms[:max_synonyms]
