"""Тесты маппинга статусов hh.ru и ложных срабатываний парсера."""
import pytest

from core.hh_sync import map_hh_status, sync_negotiations
from core.models import VacancyStatus
from core.database import VacancyRepository
from core.scraper._negotiations import _NegotiationsMixin


# ── map_hh_status ────────────────────────────────────────────────────────────

def test_map_offer():
    assert map_hh_status("вам предложили работу") == VacancyStatus.OFFER
    assert map_hh_status("Предложение о работе") == VacancyStatus.OFFER
    assert map_hh_status("job offer") == VacancyStatus.OFFER

def test_map_offer_word_no_false_positive():
    """Слово «оффер» само по себе не должно давать статус — встречается в описаниях."""
    assert map_hh_status("оффер") is None

def test_map_rejected():
    assert map_hh_status("вам отказали") == VacancyStatus.REJECTED
    assert map_hh_status("отказ") == VacancyStatus.REJECTED
    assert map_hh_status("кандидат не подошел") == VacancyStatus.REJECTED
    assert map_hh_status("кандидат не подошёл") == VacancyStatus.REJECTED

def test_map_interview():
    assert map_hh_status("приглашение на интервью") == VacancyStatus.INTERVIEW
    assert map_hh_status("вас пригласили") == VacancyStatus.INTERVIEW
    assert map_hh_status("телефонное интервью") == VacancyStatus.INTERVIEW

def test_map_applied():
    assert map_hh_status("вы откликнулись") == VacancyStatus.APPLIED
    assert map_hh_status("ваш отклик рассматривается") == VacancyStatus.APPLIED
    assert map_hh_status("отклик отправлен") == VacancyStatus.APPLIED
    assert map_hh_status("просмотрен работодателем") == VacancyStatus.APPLIED

def test_map_can_apply():
    assert map_hh_status("можно откликнуться") == VacancyStatus.DISCOVERED

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
    не должны давать статус interview/applied для неоткликнутой вакансии.
    При наличии кнопки «Откликнуться» — статус «можно откликнуться» (→ DISCOVERED).
    """
    parser = _make_parser()
    result = parser._check_vacancy_response_html(JOB_DESC_HTML, "12345")
    # Статус НЕ должен быть interview или applied — только discovered или пусто
    mapped = map_hh_status(result["hh_status"])
    assert mapped not in (VacancyStatus.INTERVIEW, VacancyStatus.APPLIED, VacancyStatus.OFFER), (
        f"Ложное срабатывание: hh_status='{result['hh_status']}' → {mapped} "
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


# ── sync_negotiations: синк двигает статус только ВПЕРЁД ──────────────────────

def test_sync_does_not_downgrade(tmp_path):
    """Страница вакансии hh.ru не отражает отклик → парсер может вернуть более
    ранний этап. Это НЕ должно откатывать реальный статус назад."""
    repo = VacancyRepository(db_path=str(tmp_path / "test.db"))
    repo.save_vacancies([{
        "id": "100", "title": "Dev", "company": "Co",
        "status": "interview",
    }])
    # hh.ru показывает более ранний этап (applied) — откат запрещён.
    negotiations = [{"vacancy_id": "100", "hh_status": "ваш отклик рассматривается",
                     "title": "Dev", "company": "Co"}]
    result = sync_negotiations(repo, negotiations)
    assert len(result.updated) == 0
    assert result.skipped_back == 1
    assert repo.get_vacancy_by_id("100")["status"] == "interview"


def test_sync_moves_forward(tmp_path):
    """Более поздний этап с hh.ru применяется (discovered → applied)."""
    repo = VacancyRepository(db_path=str(tmp_path / "test.db"))
    repo.save_vacancies([{
        "id": "101", "title": "Dev", "company": "Co", "status": "discovered",
    }])
    negotiations = [{"vacancy_id": "101", "hh_status": "ваш отклик рассматривается",
                     "title": "Dev", "company": "Co"}]
    result = sync_negotiations(repo, negotiations)
    assert len(result.updated) == 1
    assert repo.get_vacancy_by_id("101")["status"] == "applied"


def test_sync_terminal_always_applies(tmp_path):
    """Отказ/оффер работодателя применяются всегда, даже «назад» по рангу."""
    repo = VacancyRepository(db_path=str(tmp_path / "test.db"))
    repo.save_vacancies([{
        "id": "102", "title": "Dev", "company": "Co", "status": "interview",
    }])
    negotiations = [{"vacancy_id": "102", "hh_status": "вам отказали",
                     "title": "Dev", "company": "Co"}]
    result = sync_negotiations(repo, negotiations)
    assert len(result.updated) == 1
    assert repo.get_vacancy_by_id("102")["status"] == "rejected"
