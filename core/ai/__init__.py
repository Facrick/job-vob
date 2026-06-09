"""core.ai — AI-движок приложения (Groq + PDF-парсер резюме).

Используйте:
    from core.ai import LetterAnalyzer, ResumeEntity
"""
from core.ai._analyzer import LetterAnalyzer
from core.ai._resume import ResumeEntity

__all__ = ["LetterAnalyzer", "ResumeEntity"]
