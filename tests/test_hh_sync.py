"""Тесты маппинга статусов hh.ru и ложных срабатываний парсера."""
import pytest

from core.hh_sync import map_hh_status, sync_negotiations
from core.models import VacancyStatus
from core.database import VacancyRepository
from core.scraper._negotiations import _NegotiationsMixin


# ── map_hh_status ────────────────────────────────────────────────────────────

def test_map_offer():
    assert map_hh_status("оффер") == VacancyStatus.OFFER
    assert map_hh_status("Предложение о работе") == VacancyStatus.OFFER

def test_map_rejected():
    assert map_hh_status("отказ") == VacancyStatus.REJECTED
    assert map_hh_status("кандидат не подошел") == VacancyStatus.REJECTED   # е-версия
    assert map_hh_status("кандидат не подошёл") == VacancyStatus.REJECTED   # ё-версия

def test_map_interview():
    assert map_hh_status("приглашение на интервью") == VacancyStatus.INTERVIEW
    assert map_hh_status("вас пригласили") == VacancyStatus.INTERVIEW
    assert map_hh_status("телефонное интервью") == VacancyStatus.INTERVIEW

def test_map_applied():
    assert map_hh_status("ваш отклик рассматривается") == VacancyStatus.APPLIED
    assert map_hh_status("отклик отправлен") == VacancyStatus.APPLIED
    assert map_hh_status("просмотрен работодателем") == VacancyStatus.APPLIED

def test_map_empty_returns_none():
    assert map_hh_status("") is None
    assert map_hh_status(None) is None


# ── Ключевая защита от регрессии: одиночные слова НЕ дают ложных срабатываний

def test_no_false_positive_interview_word():
    """Слово «интервью» само по себе не должно давать статус INTERVIEW.

    Такие слова встречаются в описании вакансии («пройти интервью», «после интервью»)
    и ранее давали ложное повышение статуса у неоткликнутых вакансий.
    """
    assert map_hh_status("интервью") is None

def test_no_false_positive_sobesdovanie():
    """Слово «собеседование» само по себе не должно давать статус."""
    assert map_hh_status("собеседование") is None

def test_no_false_positive_priglashenie():
    """Слово «приглашение» без уточнения не должно давать статус."""
    assert map_hh_status("приглашение") is None

def test_no_false_positive_interview_en():
    """Слово 'interview' без контекста не должно давать статус."""
    assert map_hh_status("interview") is None


# ── _check_vacancy_response_html: нет статуса → пустая строка ────────────────

class _FakeMixin(_NegotiationsMixin):
    """Минимальный экземпляр для вызова метода парсинга."""

def _make_parser():
    obj = object.__new__(_FakeMixin)
    return obj

JOB_DESC_HTML = """
<html><body>
  <h1 data-qa="vacancy-title">QA Engineer</h1>
  <div data-qa="vacancy-company-name">ООО Тест</div>
  <div class="vacancy-description">
    После прохождения собеседования и интервью с командой
    вас пригласят на следующий этап. Ждём на собеседование!
  </div>
  <button data-qa="vacancy-response-link-top">Откликнуться</button>
</body></html>
"""

def test_no_false_positive_from_description():
    """Слова «собеседование» и «интервью» в описании вакансии
    не должны давать ненулевой статус для неоткликнутой вакансии."""
    parser = _make_parser()
    result = parser._check_vacancy_response_html(JOB_DESC_HTML, "12345")
    assert result["hh_status"] == "", (
        f"Ложное срабатывание: hh_status='{result['hh_status']}' "
        "для вакансии без отклика"
    )
    assert result["title"] == "QA Engineer"
    assert result["company"] == "ООО Тест"


APPLIED_HTML = """
<html><body>
  <h1 data-qa="vacancy-title">QA Engineer</h1>
  <div data-qa="vacancy-company-name">Яндекс</div>
  <div data-qa="vacancy-response-status">Ваш отклик рассматривается</div>
  <div class="vacancy-description">
    Обязанности: тестировать продукты. Требования: опыт от 2 лет.
  </div>
</body></html>
"""

def test_detects_applied_status_via_data_qa():
    """data-qa=vacancy-response-status должен распознаваться как APPLIED."""
    parser = _make_parser()
    result = parser._check_vacancy_response_html(APPLIED_HTML, "99999")
    assert result["hh_status"] != "", "Статус не определён для вакансии с откликом"
    assert map_hh_status(result["hh_status"]) == VacancyStatus.APPLIED


# ── sync_negotiations: понижение статуса теперь разрешено ────────────────────

def test_sync_allows_status_downgrade(tmp_path):
    """Если hh.ru показывает более низкий статус — CRM обновляется.
    Вакансия может переоткрыться, отклик сброситься."""
    repo = VacancyRepository(db_path=str(tmp_path / "test.db"))
    repo.save_vacancies([{
        "id": "100", "title": "Dev", "company": "Co",
        "status": "interview",  # был interview
    }])
    # hh.ru теперь показывает только applied
    negotiations = [{"vacancy_id": "100", "hh_status": "ваш отклик рассматривается",
                     "title": "Dev", "company": "Co"}]
    result = sync_negotiations(repo, negotiations)
    assert len(result.updated) == 1
    assert result.updated[0]["new"] == "applied"
    assert repo.get_vacancy_by_id("100")["status"] == "applied"
