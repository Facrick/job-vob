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


def test_mock_interview_roundtrip(repo):
    history = [{"role": "assistant", "content": "вопрос"},
               {"role": "user", "content": "ответ"}]
    repo.save_mock_interview("7", history)
    assert repo.get_mock_interview("7") == history


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
