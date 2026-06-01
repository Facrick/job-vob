"""Доменные модели и перечисления приложения.

Здесь живёт единственный источник правды для:
- статусов вакансий (VacancyStatus) — раньше были magic strings в 3 файлах;
- структуры вакансии (Vacancy) — раньше гонялся нетипизированный dict.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional


class VacancyStatus(str, Enum):
    """Статусы вакансии в Kanban-воронке.

    Наследование от str делает Enum совместимым со строками:
    сравнение `status == VacancyStatus.DISCOVERED` и запись в SQLite
    работают без изменений в БД.
    """
    DISCOVERED = "discovered"
    PROCESSED = "processed"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"

    def __str__(self) -> str:  # чтобы f-строки и SQL получали чистое значение
        return self.value


@dataclass
class Vacancy:
    """Типизированное представление вакансии.

    Заменяет нетипизированный dict, который раньше ходил через весь стек.
    IDE подсказывает все поля, опечатка в имени ловится статически.
    """
    id: str
    title: str
    company: str = "Не указана"
    description: str = ""
    skills: str = ""
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    status: str = VacancyStatus.DISCOVERED.value
    notes: str = ""

    @classmethod
    def from_row(cls, row: Optional[dict]) -> Optional["Vacancy"]:
        """Создаёт Vacancy из строки БД (sqlite3.Row -> dict).

        Возвращает None, если строки нет — сохраняет прежнее поведение
        репозитория (get_vacancy_by_id мог вернуть None).
        """
        if row is None:
            return None
        return cls(
            id=row["id"],
            title=row.get("title") or "",
            company=row.get("company") or "Не указана",
            description=row.get("description") or "",
            skills=row.get("skills") or "",
            salary_min=row.get("salary_min"),
            salary_max=row.get("salary_max"),
            status=row.get("status") or VacancyStatus.DISCOVERED.value,
            notes=row.get("notes") or "",
        )

    def to_dict(self) -> dict:
        """Сериализация в dict (для сохранения в БД)."""
        return asdict(self)
