"""Общие утилиты, переиспользуемые между модулями core.

html_to_markdown() — конвертирует HTML из handbook.json в Markdown
для отображения в ft.Markdown без сторонних зависимостей.

Единственная реализация parse_salary_text() — раньше логика была
продублирована в ai_engine.VacancySalaryParser и
parser.HHParser._parse_salary_text с расходящимся поведением.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

# ──────────────────────────────────────────────────────────────────────────────
#  HTML → Markdown
# ──────────────────────────────────────────────────────────────────────────────


class _HtmlToMd(HTMLParser):
    """Минимальный конвертер HTML → Markdown без сторонних зависимостей."""

    _BLOCK = {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "li",
        "br",
        "ul",
        "ol",
        "div",
        "blockquote",
    }
    _HEADING_PREFIX = {
        "h1": "# ",
        "h2": "## ",
        "h3": "### ",
        "h4": "#### ",
        "h5": "##### ",
        "h6": "###### ",
    }

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._stack: list[str] = []
        self._in_li = False
        self._in_pre = False  # внутри блока кода <pre> не экранируем

    def handle_starttag(self, tag, attrs):
        self._stack.append(tag)
        if tag == "pre":
            self._in_pre = True
            self._parts.append("\n```\n")
        elif tag in self._HEADING_PREFIX:
            self._parts.append("\n" + self._HEADING_PREFIX[tag])
        elif tag == "li":
            self._in_li = True
            self._parts.append("\n- ")
        elif tag == "br":
            self._parts.append("  \n")
        elif tag == "b" or tag == "strong":
            self._parts.append("**")
        elif tag == "i" or tag == "em":
            self._parts.append("*")
        elif tag == "code":
            if not self._in_pre:  # внутри <pre> код уже в ``` ```
                self._parts.append("`")
        elif tag == "p":
            self._parts.append("\n")

    def handle_endtag(self, tag):
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()
        if tag == "pre":
            self._parts.append("\n```\n")
            self._in_pre = False
        elif tag in self._HEADING_PREFIX or tag in ("p", "li", "ul", "ol", "div"):
            self._parts.append("\n")
            if tag == "li":
                self._in_li = False
        elif tag in ("b", "strong"):
            self._parts.append("**")
        elif tag in ("i", "em"):
            self._parts.append("*")
        elif tag == "code":
            if not self._in_pre:
                self._parts.append("`")

    def handle_data(self, data):
        self._parts.append(data)

    def result(self) -> str:
        raw = "".join(self._parts)
        # убираем тройные+ пустые строки
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def html_to_markdown(html: str) -> str:
    """Конвертирует HTML-строку в Markdown.

    Используется для отображения ответов учебника в ft.Markdown.
    """
    if not html or not html.strip():
        return ""
    # Если нет HTML-тегов — возвращаем как есть
    if "<" not in html:
        return html
    parser = _HtmlToMd()
    parser.feed(html)
    return parser.result()


def strip_html(html: str) -> str:
    """Грубо конвертирует HTML в читаемый плоский текст.

    Описание вакансии из API hh.ru приходит в HTML; в UI оно показывается
    как обычный текст (ft.Text), поэтому теги нужно убрать, а блочные
    элементы превратить в переносы строк.
    """
    if not html:
        return ""
    import html as _html

    text = html
    text = re.sub(r"(?i)<li[^>]*>", "\n• ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|ul|ol|h[1-6]|tr)>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)  # все оставшиеся теги
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def parse_salary_text(salary_text: str) -> tuple[int | None, int | None]:
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


def extract_salary_from_resume(text: str) -> int | None:
    """Извлекает ожидаемую зарплату из текста резюме.

    Возвращает None, если ничего не найдено — вызывающий код решает,
    что подставить (обычно дефолт из AppConfig).
    """
    patterns = [
        # Метка (зарплата/доход/зп/ожидания) + до 8 нецифровых разделителей + число.
        # Раньше требовалось число СРАЗУ после "зарплат", из-за чего частое
        # "Зарплата: 180 000" не находилось (мешало окончание "а:").
        r"(?:доход|зарплат|зп|ожидани\w*)[^\d]{0,8}(\d{1,3}(?:[\s ]?\d{3})*)",
        r"(\d{1,3}(?:[\s ]?\d{3})*)\s*руб",
        r"(\d{1,3}(?:[\s ]?\d{3})*)\s*₽",
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
