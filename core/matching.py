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


def _tokenize(text: str) -> list[str]:
    """Слова ≥2 символов; +/#/./ остаются внутри тех-терминов (ci/cd, c++, .net)."""
    return re.findall(r"[a-zа-яё0-9#.+/]{2,}", (text or "").lower())


def _fuzzy_match(a: str, b: str, n: int = 5) -> bool:
    """Совпадение по общему префиксу (корню) — чтобы ловить словоформы.

    Короткие слова (≤4 символов, напр. java, sql, api) — только точное совпадение,
    иначе ложные срабатывания. Для длинных достаточно общего префикса ≥5 символов
    (тестирование/тестирования, автоматизация/автоматизировать).
    """
    if min(len(a), len(b)) <= 4:
        return a == b
    i, m = 0, min(len(a), len(b))
    while i < m and a[i] == b[i]:
        i += 1
    return i >= n


def _token_present(token: str, rset: set[str], rlist: list[str]) -> bool:
    if token in rset:
        return True
    if len(token) <= 4:
        return False
    return any(_fuzzy_match(token, rt) for rt in rlist)


def _skill_coverage(skill: str, text_lower: str, rset: set[str], rlist: list[str]) -> float:
    """Доля «покрытия» навыка резюме (0..1): точная фраза = 1.0, иначе доля
    значимых слов навыка, найденных в резюме (с учётом словоформ)."""
    s = skill.strip().lower()
    if not s:
        return 0.0
    if _present(s, text_lower):
        return 1.0
    toks = [t for t in _tokenize(s) if t not in _STOPWORDS]
    if not toks:
        return 0.0
    matched = sum(1 for t in toks if _token_present(t, rset, rlist))
    return matched / len(toks)


def _title_terms(title: str) -> list[str]:
    return [t for t in _tokenize(title) if t not in _STOPWORDS]


def compute_match_score(resume_text: str, vacancy: dict) -> int:
    """Оценка соответствия резюме вакансии в процентах (0–100).

    • Нет резюме → 0 (не с чем сравнивать).
    • Есть ключевые навыки → средняя «покрытость» навыков резюме (75%) +
      доля слов названия, найденных в резюме (25%).
    • Навыки не заданы → опираемся только на слова названия.

    Учитываются словоформы (общий корень) и частичное совпадение многословных
    навыков, поэтому оценка ближе к реальной, чем дословное сравнение.
    """
    text = (resume_text or "").lower()
    if not text.strip():
        return 0

    rlist = _tokenize(text)
    rset = set(rlist)

    skills_raw = (vacancy.get("skills") or "")
    skills = [
        s.strip() for s in skills_raw.split(",")
        if s.strip() and s.strip().lower() not in _EMPTY_SKILLS
    ]

    title_terms = set(_title_terms(vacancy.get("title", "")))
    title_score = (
        sum(1 for t in title_terms if _token_present(t, rset, rlist)) / len(title_terms)
        if title_terms else 0.0
    )

    if skills:
        skills_score = sum(
            _skill_coverage(s, text, rset, rlist) for s in skills
        ) / len(skills)
        score = 0.75 * skills_score + 0.25 * title_score
    else:
        # Без явных навыков — оценка только по названию.
        score = title_score

    return round(max(0.0, min(1.0, score)) * 100)
