"""core.ai_engine — обратная совместимость.

Реальная реализация перенесена в core.ai (пакет).
Все импорты вида ``from core.ai_engine import LetterAnalyzer`` продолжают работать.
"""
from core.ai import LetterAnalyzer, ResumeEntity  # noqa: F401

__all__ = ["LetterAnalyzer", "ResumeEntity"]
