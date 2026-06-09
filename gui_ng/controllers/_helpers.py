"""Вспомогательные функции уровня модуля (не методы класса)."""
import re

_HH_UNSAFE = re.compile(
    r"<(script|iframe|object|embed|form|input|button|link|style)[^>]*>.*?</\1>|"
    r"<(script|iframe|object|embed|form|input|button|link|style)[^>]*/?>",
    re.IGNORECASE | re.DOTALL,
)
_HH_ATTR_UNSAFE = re.compile(
    r'\s+on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE
)


def _sanitize_hh_html(html: str) -> str:
    """Оставляет форматирование hh.ru — убирает скрипты, iframe, обработчики событий."""
    if not html:
        return ""
    s = _HH_UNSAFE.sub("", html)
    s = _HH_ATTR_UNSAFE.sub("", s)
    return s.strip()


def _q(hex_color: str) -> str:
    """Quasar принимает цвет как имя или как hex — отдаём hex без изменений."""
    return hex_color
