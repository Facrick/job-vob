"""Словарь синонимов должностей для расширенного поиска вакансий.

expand_query(text) возвращает [text] + подходящие синонимы из словаря.
Поиск по ключу нечувствителен к регистру и обрезает пробелы.
"""
from __future__ import annotations

import re

# Ключ — нормализованное (lower) название роли.
# Значения — ТОЛЬКО варианты написания/перевода ТОЙ ЖЕ роли (рус/англ,
# раскладка, аббревиатура), а НЕ смежные профессии. Так поиск «scrum master»
# не приводит к выдаче QA, agile coach и прочих несвязанных вакансий.
# ВАЖНО: ключ — ОДНА каноническая роль (один пункт в выпадающем списке).
# Значения — все варианты написания/языка/раскладки ТОЙ ЖЕ роли, по которым
# надо искать. Каждый вариант написания НЕ заводится отдельным ключом, иначе
# в списке появятся дубли одной профессии (scrum master / scrum мастер / …).
_SYNONYMS: dict[str, list[str]] = {
    # ── QA / тестирование ────────────────────────────────────────────────
    "qa engineer": ["QA инженер", "тестировщик ПО", "инженер по тестированию"],
    "aqa": ["AQA инженер", "automation QA engineer", "автоматизатор тестирования"],
    "fullstack aqa": ["fullstack automation QA", "fullstack qa automation", "фуллстек AQA"],
    "sdet": ["SDET engineer"],

    # ── Разработка (Backend) ──────────────────────────────────────────────
    "python developer": ["python разработчик", "питон разработчик"],
    "java developer": ["java разработчик"],
    "golang developer": ["go разработчик", "golang разработчик", "go developer"],
    "backend developer": ["backend разработчик", "бэкенд разработчик"],
    "fullstack developer": ["fullstack разработчик", "full stack developer", "фуллстек разработчик"],

    # ── Разработка (Frontend) ─────────────────────────────────────────────
    "frontend developer": ["frontend разработчик", "фронтенд разработчик"],
    "react developer": ["react разработчик"],
    "vue developer": ["vue разработчик"],

    # ── DevOps / Infra / SRE ─────────────────────────────────────────────
    "devops engineer": ["DevOps инженер", "инженер DevOps", "девопс инженер"],
    "sre engineer": ["SRE инженер", "site reliability engineer"],

    # ── Data ─────────────────────────────────────────────────────────────
    "data scientist": ["дата сайентист", "data scientist"],
    "data engineer": ["инженер данных", "дата инженер"],
    "data analyst": ["аналитик данных", "дата аналитик"],
    "ml engineer": ["machine learning engineer", "ML инженер"],

    # ── Управление / Agile / PM ───────────────────────────────────────────
    "scrum master": ["scrum мастер", "скрам мастер", "скрам-мастер"],
    "product manager": ["продакт менеджер", "продуктовый менеджер", "менеджер продукта"],
    "product owner": ["продакт оунер", "владелец продукта"],
    "project manager": ["менеджер проекта", "руководитель проекта", "проджект менеджер"],
    "agile coach": ["agile коуч", "аджайл коуч"],

    # ── Аналитика / BA ────────────────────────────────────────────────────
    "business analyst": ["бизнес аналитик", "бизнес-аналитик"],
    "system analyst": ["системный аналитик", "systems analyst"],

    # ── Безопасность ─────────────────────────────────────────────────────
    "security engineer": ["инженер по безопасности", "специалист по информационной безопасности"],
    "pentester": ["penetration tester", "пентестер", "специалист по пентесту"],

    # ── Мобильная разработка ──────────────────────────────────────────────
    "ios developer": ["ios разработчик"],
    "android developer": ["android разработчик"],
    "mobile developer": ["мобильный разработчик"],
    "flutter developer": ["flutter разработчик"],

    # ── UX/UI ─────────────────────────────────────────────────────────────
    "ux designer": ["ux дизайнер", "ux/ui дизайнер"],
    "ui designer": ["ui дизайнер", "ux/ui дизайнер"],
    "product designer": ["продуктовый дизайнер"],
}


# Аккуратные подписи для ролей в выпадающем списке (где .title() портит регистр).
_ROLE_LABELS: dict[str, str] = {
    "qa engineer": "QA Engineer",
    "aqa": "AQA",
    "fullstack aqa": "Fullstack AQA",
    "sdet": "SDET",
    "devops engineer": "DevOps Engineer",
    "sre engineer": "SRE Engineer",
    "ml engineer": "ML Engineer",
    "ios developer": "iOS Developer",
    "ux designer": "UX Designer",
    "ui designer": "UI Designer",
}


def role_options() -> dict[str, str]:
    """Словарь {значение: подпись} ролей для ui.select в GUI.

    Значение — нормализованный ключ словаря синонимов (lower), поэтому
    expand_query(value) сразу найдёт привязанную группу синонимов.
    """
    return {key: _ROLE_LABELS.get(key, key.title()) for key in _SYNONYMS}


# Слова-связки, не несущие смысла роли — не должны влиять на валидацию названия.
# («python developer» не обязан содержать в заголовке слово «developer».)
_STOPWORDS: frozenset[str] = frozenset({
    "developer", "разработчик", "engineer", "инженер", "specialist",
    "специалист", "manager", "менеджер", "по", "and", "of", "the",
})

# Минимальная длина значимого слова — короче считаем шумом (и/в/qa — исключение ниже).
_MIN_WORD_LEN = 3
# Короткие, но значимые токены (аббревиатуры ролей), которые нельзя выкидывать по длине.
_SHORT_KEEP: frozenset[str] = frozenset({"qa", "ml", "ux", "ui", "go", "ba", "pm", "ios"})


def _tokenize(text: str) -> list[str]:
    """Разбивает текст на нормализованные слова (lower, только буквы/цифры)."""
    return re.findall(r"[\wа-яё]+", text.lower())


def significant_words(text: str) -> set[str]:
    """Значимые слова запроса + всей его группы синонимов.

    Используется для валидации заголовка вакансии: hh.ru ищет по описанию и
    компании, поэтому в выдачу попадают вакансии, где запрос не относится к
    названию. Считаем вакансию релевантной, если её заголовок содержит хотя бы
    одно из этих слов.

    >>> "qa" in significant_words("QA Engineer")
    True
    >>> "тестировщик" in significant_words("QA Engineer")  # из синонимов
    True
    """
    words: set[str] = set()
    for phrase in expand_query(text):
        for tok in _tokenize(phrase):
            if tok in _SHORT_KEEP:
                words.add(tok)
            elif len(tok) >= _MIN_WORD_LEN and tok not in _STOPWORDS:
                words.add(tok)
    return words


def title_matches_query(title: str, text: str) -> bool:
    """True, если заголовок вакансии содержит хотя бы одно значимое слово запроса.

    Если у запроса нет значимых слов (например, состоит только из стоп-слов),
    фильтр пропускает всё — лучше показать лишнее, чем потерять всё.

    >>> title_matches_query("Senior QA Engineer", "QA Engineer")
    True
    >>> title_matches_query("Курьер по доставке еды", "Python Developer")
    False
    """
    keywords = significant_words(text)
    if not keywords:
        return True
    title_tokens = set(_tokenize(title))
    return bool(keywords & title_tokens)


def expand_query(text: str, max_synonyms: int = 3) -> list[str]:
    """Возвращает [text] + синонимы (не более max_synonyms).

    Если подходящего ключа в словаре нет — возвращает [text].

    >>> expand_query("QA Engineer")
    ['QA Engineer', 'QA инженер', 'тестировщик ПО', 'инженер по тестированию']
    >>> expand_query("scrum master")
    ['scrum master', 'scrum мастер', 'скрам мастер', 'скрам-мастер']
    >>> expand_query("неизвестная роль")
    ['неизвестная роль']
    """
    key = text.strip().lower()
    synonyms = _SYNONYMS.get(key, [])
    return [text] + synonyms[:max_synonyms]
