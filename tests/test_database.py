"""Тесты репозитория вакансий и CSV-экспорта на временной БД."""
import csv

import pytest

from core.database import DataExporter, VacancyRepository
from core.models import VacancyStatus


@pytest.fixture
def repo(tmp_path):
    return VacancyRepository(db_path=str(tmp_path / "test.db"))


def _vacancy(vid="1", status="discovered"):
    return {
        "id": vid, "title": "QA Engineer", "company": "ООО Тест",
        "salary_min": 100000, "salary_max": 200000,
        "description": "desc", "skills": "pytest, SQL", "status": status,
    }


def test_save_and_get(repo):
    repo.save_vacancies([_vacancy("10")])
    row = repo.get_vacancy_by_id("10")
    assert row["title"] == "QA Engineer"
    assert row["salary_min"] == 100000


def test_save_is_idempotent(repo):
    repo.save_vacancies([_vacancy("10")])
    repo.save_vacancies([_vacancy("10")])  # повторно — без дублей (ON CONFLICT)
    assert len(repo.get_vacancies_filtered("all")) == 1


def test_status_filter_and_update(repo):
    repo.save_vacancies([_vacancy("1"), _vacancy("2")])
    repo.update_status("2", "applied")
    assert len(repo.get_vacancies_filtered("all")) == 2
    assert len(repo.get_vacancies_filtered("discovered")) == 1
    assert repo.get_vacancies_filtered("applied")[0]["id"] == "2"


def test_update_status_accepts_enum(repo):
    repo.save_vacancies([_vacancy("1")])
    repo.update_status("1", VacancyStatus.OFFER)  # str(Enum) → чистое значение
    assert repo.get_vacancy_by_id("1")["status"] == "offer"


def test_clear_discovered(repo):
    repo.save_vacancies([_vacancy("1", "discovered"), _vacancy("2", "applied")])
    repo.clear_discovered_vacancies()
    remaining = repo.get_vacancies_filtered("all")
    assert [v["id"] for v in remaining] == ["2"]


def test_cover_letter_roundtrip(repo):
    repo.save_vacancies([_vacancy("5")])
    repo.save_cover_letter("5", "текст письма", "рекомендации")
    cl = repo.get_cover_letter("5")
    assert cl["letter_text"] == "текст письма"
    assert cl["recommendations"] == "рекомендации"


def test_cover_letter_absent(repo):
    assert repo.get_cover_letter("999") is None


def test_letter_history_saves_versions(repo):
    repo.save_vacancies([_vacancy("5")])
    repo.save_cover_letter("5", "версия 1", "рек 1")
    repo.save_cover_letter("5", "версия 2", "рек 2")
    repo.save_cover_letter("5", "версия 3", "рек 3")
    history = repo.get_letter_history("5")
    assert len(history) == 3
    # Новые первыми
    assert history[0]["letter_text"] == "версия 3"
    assert history[-1]["letter_text"] == "версия 1"


def test_letter_history_trims_to_max(repo):
    repo.save_vacancies([_vacancy("5")])
    max_v = repo._MAX_LETTER_VERSIONS
    for i in range(max_v + 2):
        repo.save_cover_letter("5", f"версия {i}", "")
    history = repo.get_letter_history("5")
    assert len(history) == max_v
    # Самая новая должна быть первой
    assert history[0]["letter_text"] == f"версия {max_v + 1}"


def test_letter_history_empty_for_new_vacancy(repo):
    repo.save_vacancies([_vacancy("5")])
    assert repo.get_letter_history("5") == []


def test_mock_interview_roundtrip(repo):
    history = [{"role": "assistant", "content": "вопрос"},
               {"role": "user", "content": "ответ"}]
    repo.save_mock_interview("7", history)
    assert repo.get_mock_interview("7") == history


def test_delete_vacancy_removes_vacancy_and_related(repo):
    repo.save_vacancies([_vacancy("42")])
    repo.save_cover_letter("42", "письмо", "рекомендации")
    repo.save_mock_interview("42", [{"role": "user", "content": "вопрос"}])

    repo.delete_vacancy("42")

    assert repo.get_vacancy_by_id("42") is None
    assert repo.get_cover_letter("42") is None
    assert repo.get_mock_interview("42") is None
    assert len(repo.get_vacancies_filtered("all")) == 0


def test_delete_vacancy_nonexistent_is_safe(repo):
    """Удаление несуществующей вакансии не бросает исключение."""
    repo.delete_vacancy("no-such-id")  # должно пройти без ошибок


def test_delete_vacancy_does_not_affect_others(repo):
    repo.save_vacancies([_vacancy("1"), _vacancy("2")])
    repo.delete_vacancy("1")
    remaining = repo.get_vacancies_filtered("all")
    assert len(remaining) == 1
    assert remaining[0]["id"] == "2"


def test_export_csv(repo, tmp_path):
    repo.save_vacancies([_vacancy("1"), _vacancy("2")])
    path = tmp_path / "out.csv"
    ok, msg = DataExporter(repo).export_discovered_to_csv(str(path))
    assert ok is True
    assert path.exists()
    with open(path, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0][0] == "ID"          # заголовок
    assert len(rows) == 3              # 1 заголовок + 2 вакансии
