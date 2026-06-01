"""Общие утилиты, переиспользуемые между модулями core.

Единственная реализация parse_salary_text() — раньше логика была
продублирована в ai_engine.VacancySalaryParser и
parser.HHParser._parse_salary_text с расходящимся поведением.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


def parse_salary_text(salary_text: str) -> Tuple[Optional[int], Optional[int]]:
    """Парсит зарплатный диапазон из произвольной строки hh.ru.

    Поддерживает форматы:
        "от 100 000 до 200 000 ₽" -> (100000, 200000)
        "от 150 000 руб"          -> (150000, None)
        "до 180 000 ₽"            -> (None, 180000)
        "120 000 – 160 000"       -> (120000, 160000)
        "90000"                   -> (90000, None)
        "" / "з/п не указана"     -> (None, None)

    Returns:
        Кортеж (salary_min, salary_max); любой элемент может быть None.
    """
    if not salary_text:
        return None, None

    # Убираем неразрывные пробелы, обычные пробелы, валюту
    cleaned = re.sub(r"[\xa0\s₽]", "", salary_text)
    cleaned = re.sub(r"(руб|руб\.|rub)", "", cleaned, flags=re.IGNORECASE)

    # 1. Диапазон через тире/дефис: 120000-160000, 120000–160000, 120000—160000
    range_match = re.search(r"(\d+)[-–—](\d+)", cleaned)
    if range_match:
        return int(range_match.group(1)), int(range_match.group(2))

    # 2. "от X" (возможно вместе с "до Y")
    from_match = re.search(r"от(\d+)", cleaned)
    if from_match:
        to_match = re.search(r"до(\d+)", cleaned)
        salary_max = int(to_match.group(1)) if to_match else None
        return int(from_match.group(1)), salary_max

    # 3. Только "до Y"
    to_match = re.search(r"до(\d+)", cleaned)
    if to_match:
        return None, int(to_match.group(1))

    # 4. Просто одно или несколько чисел
    digits = [int(d) for d in re.findall(r"\d+", cleaned)]
    if len(digits) == 1:
        return digits[0], None
    if len(digits) >= 2:
        return digits[0], digits[1]

    return None, None


def extract_salary_from_resume(text: str) -> Optional[int]:
    """Извлекает ожидаемую зарплату из текста резюме.

    Возвращает None, если ничего не найдено — вызывающий код решает,
    что подставить (обычно дефолт из AppConfig).
    """
    patterns = [
        r"(?:доход|зарплат|зп)[:\s]*(\d{1,3}(?:[\s]?\d{3})*)",
        r"(\d{1,3}(?:[\s]?\d{3})*)[\s]*руб",
        r"(\d{1,3}(?:[\s]?\d{3})*)[\s]*₽",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            salary_str = re.sub(r"\s+", "", match.group(1))
            try:
                return int(salary_str)
            except ValueError:
                continue
    return None
