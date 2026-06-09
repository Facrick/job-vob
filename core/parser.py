"""core.parser — обратная совместимость.

Реальная реализация перенесена в core.scraper (пакет с миксинами).
Все импорты вида ``from core.parser import HHParser`` продолжают работать.
"""
from core.scraper import HHParser, HumanInteractionEngine, VacancyInfo  # noqa: F401

__all__ = ["HHParser", "VacancyInfo", "HumanInteractionEngine"]
