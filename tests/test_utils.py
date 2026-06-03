"""Тесты чистых утилит: парсинг зарплат, извлечение из резюме, HTML→Markdown."""
import pytest

from core.utils import extract_salary_from_resume, html_to_markdown, parse_salary_text


@pytest.mark.parametrize("text, expected", [
    ("от 100 000 до 200 000 ₽", (100000, 200000)),
    ("от 150 000 руб",          (150000, None)),
    ("до 180 000 ₽",            (None, 180000)),
    ("120 000 – 160 000",       (120000, 160000)),
    ("90000",                   (90000, None)),
    ("",                        (None, None)),
    ("з/п не указана",          (None, None)),
])
def test_parse_salary_text(text, expected):
    assert parse_salary_text(text) == expected


def test_extract_salary_from_resume_found():
    assert extract_salary_from_resume("Зарплата: 180 000") == 180000
    assert extract_salary_from_resume("ожидания 200000 руб") == 200000


def test_extract_salary_from_resume_absent():
    assert extract_salary_from_resume("без цифр о деньгах") is None


def test_html_to_markdown_blocks():
    md = html_to_markdown("<h3>Заголовок</h3><ul><li>раз</li><li>два</li></ul>")
    assert "### Заголовок" in md
    assert "- раз" in md and "- два" in md


def test_html_to_markdown_inline():
    md = html_to_markdown("<p><b>жирный</b> и <code>код</code></p>")
    assert "**жирный**" in md
    assert "`код`" in md


def test_html_to_markdown_pre_code_block():
    md = html_to_markdown("<pre><code>line1\nline2</code></pre>")
    assert "```" in md
    assert "line1" in md and "line2" in md
    # внутри fenced-блока не должно быть инлайновых одиночных бэктиков вокруг кода
    assert "`line1`" not in md


def test_html_to_markdown_plain_passthrough():
    assert html_to_markdown("просто текст") == "просто текст"
    assert html_to_markdown("") == ""
