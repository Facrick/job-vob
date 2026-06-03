"""Анализ навыков рынка по базе собранных вакансий.

Источник данных — поле skills (ключевые навыки из hh.ru API) каждой вакансии.
Определение грейда — по ключевым словам в названии вакансии.
Без LLM и сетевых запросов: всё из локальной БД.
"""
from __future__ import annotations

from collections import defaultdict

_SKIP = {"не указаны", "не указано", "—", "-", ""}

# Канонические QA-навыки для поиска в тексте описания (фолбэк когда skills пуст).
# Ключ — regexp-паттерн (lower), значение — отображаемое имя.
_KNOWN_SKILLS: dict[str, str] = {
    r"python":          "Python",
    r"java\b":          "Java",
    r"javascript":      "JavaScript",
    r"selenium":        "Selenium",
    r"playwright":      "Playwright",
    r"cypress":         "Cypress",
    r"appium":          "Appium",
    r"pytest":          "pytest",
    r"junit":           "JUnit",
    r"testng":          "TestNG",
    r"rest.?assured":   "REST Assured",
    r"postman":         "Postman",
    r"jmeter":          "JMeter",
    r"gatling":         "Gatling",
    r"k6\b":            "k6",
    r"sql\b":           "SQL",
    r"postgresql":      "PostgreSQL",
    r"mysql":           "MySQL",
    r"mongodb":         "MongoDB",
    r"docker":          "Docker",
    r"kubernetes":      "Kubernetes",
    r"jenkins":         "Jenkins",
    r"gitlab\s*ci":     "GitLab CI",
    r"github\s*actions":"GitHub Actions",
    r"jira":            "Jira",
    r"confluence":      "Confluence",
    r"allure":          "Allure",
    r"swagger":         "Swagger",
    r"graphql":         "GraphQL",
    r"grpc":            "gRPC",
    r"kafka":           "Kafka",
    r"rabbitmq":        "RabbitMQ",
    r"linux":           "Linux",
    r"git\b":           "Git",
    r"agile":           "Agile",
    r"scrum":           "Scrum",
    r"ci/?cd":          "CI/CD",
    r"api.{0,10}тест|api.{0,10}test": "API тестирование",
    r"нагрузочн|load.{0,5}test":      "Нагрузочное тестирование",
    r"mobile.{0,5}test|мобильн.{0,8}тест": "Mobile тестирование",
}

_GRADE_PATTERNS: list[tuple[str, list[str]]] = [
    ("Senior/Lead", ["senior", "сеньор", "sr.", "lead", "лид", "head",
                     "chief", "principal", "architect"]),
    ("Junior",      ["junior", "джун", "jr.", "стажёр", "стажер",
                     "intern", "trainee", "начинающий"]),
]
GRADE_COLORS = {
    "Junior":      "BLUE_300",
    "Middle":      "INDIGO_400",
    "Senior/Lead": "PURPLE_400",
}


def detect_grade(title: str) -> str:
    t = (title or "").lower()
    for grade, patterns in _GRADE_PATTERNS:
        if any(p in t for p in patterns):
            return grade
    return "Middle"


import re as _re


def _skills_from_description(text: str) -> list[str]:
    """Ищет известные QA-навыки в тексте описания вакансии."""
    t = (text or "").lower()
    found = []
    for pattern, display in _KNOWN_SKILLS.items():
        if _re.search(pattern, t):
            found.append(display)
    return found


def extract_top_skills(
    vacancies: list[dict],
    top_n: int = 20,
    min_count: int = 2,
) -> list[dict]:
    """Топ-N навыков по частоте из поля skills вакансий.

    Если у вакансии skills пуст или "Не указаны" — ищет навыки
    в description по списку известных QA-технологий (_KNOWN_SKILLS).

    Возвращает список:
      [{"skill": str, "count": int,
        "grades": {"Junior": n, "Middle": n, "Senior/Lead": n}}, ...]
    Отсортирован по убыванию count.
    """
    counts: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "grades": defaultdict(int)}
    )

    for v in vacancies:
        grade = detect_grade(v.get("title", ""))
        raw = v.get("skills") or ""
        skills = [s.strip() for s in raw.split(",")]
        skills = [s for s in skills if s and s.lower() not in _SKIP and len(s) > 1]

        if not skills:
            skills = _skills_from_description(v.get("description", ""))

        seen: set[str] = set()
        for skill in skills:
            key = skill.lower()
            if key in seen:
                continue
            seen.add(key)
            counts[skill]["count"] += 1
            counts[skill]["grades"][grade] += 1

    filtered = [
        (skill, data)
        for skill, data in counts.items()
        if data["count"] >= min_count
    ]
    filtered.sort(key=lambda x: -x[1]["count"])

    return [
        {"skill": skill, "count": data["count"], "grades": dict(data["grades"])}
        for skill, data in filtered[:top_n]
    ]
