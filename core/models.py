"""Доменные перечисления приложения.

Единственный источник правды для статусов вакансий (VacancyStatus) —
раньше были magic strings, разбросанные по нескольким файлам.
"""
from __future__ import annotations

from enum import StrEnum


class VacancyStatus(StrEnum):
    """Статусы вакансии в Kanban-воронке.

    StrEnum: значение == строка, поэтому сравнение
    `status == VacancyStatus.DISCOVERED`, f-строки и запись в SQLite
    работают без изменений в БД (str(VacancyStatus.OFFER) == "offer").
    """
    DISCOVERED = "discovered"
    PROCESSED = "processed"
    APPLIED = "applied"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
