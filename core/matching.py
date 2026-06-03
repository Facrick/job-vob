"""Быстрый офлайн match-score соответствия резюме ↔ вакансия (0–100%).

Детерминированно, без LLM и сети: оценка строится на пересечении ключевых
навыков вакансии с текстом резюме (+ небольшой вклад слов из названия).
Используется, чтобы мгновенно отсортировать ленту вакансий по релевантности.
Глубокий ИИ-разбор (LetterAnalyzer.analyze_vacancy) остаётся для выбранной
вакансии по клику.
"""
from __future__ import annotations

import re

# Частые служебные слова, которые не должны влиять на оценку названия.
_STOPWORDS = {
    "по", "и", "в", "для", "на", "с", "от", "до", "the", "a", "an",
    "of", "to", "and", "or", "qa",  # «qa» слишком общее для названия
}

# Плейсхолдеры, означающие «навыки не заданы».
_EMPTY_SKILLS = {"", "не указаны", "не указано", "—", "-"}


def _present(term: str, text_lower: str) -> bool:
    """Есть ли термин в тексте как отдельное «слово» (учёт + # . / в тех-терминах)."""
    t = term.strip().lower()
    if not t:
        return False
    pattern = r"(?<![a-zа-яё0-9])" + re.escape(t) + r"(?![a-zа-яё0-9])"
    return re.search(pattern, text_lower) is not None


def _title_terms(title: str) -> list[str]:
    tokens = re.findall(r"[a-zа-яё0-9#.+/_-]{2,}", (title or "").lower())
    return [t for t in tokens if t not in _STOPWORDS]


def compute_match_score(resume_text: str, vacancy: dict) -> int:
    """Оценка соответствия резюме вакансии в процентах (0–100).

    • Нет резюме → 0 (не с чем сравнивать).
    • Есть ключевые навыки у вакансии → доля навыков, найденных в резюме (75%)
      + доля слов названия, найденных в резюме (25%).
    • Навыки не заданы → опираемся только на слова названия.
    """
    text = (resume_text or "").lower()
    if not text.strip():
        return 0

    skills_raw = (vacancy.get("skills") or "")
    skills = [
        s.strip() for s in skills_raw.split(",")
        if s.strip() and s.strip().lower() not in _EMPTY_SKILLS
    ]

    title_terms = set(_title_terms(vacancy.get("title", "")))
    title_score = (
        sum(1 for t in title_terms if _present(t, text)) / len(title_terms)
        if title_terms else 0.0
    )

    if skills:
        matched = sum(1 for s in skills if _present(s, text))
        skills_score = matched / len(skills)
        score = 0.75 * skills_score + 0.25 * title_score
    else:
        # Без явных навыков — оценка только по названию.
        score = title_score

    return round(max(0.0, min(1.0, score)) * 100)
