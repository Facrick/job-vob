"""Тесты match-score (офлайн, детерминированно) и сортировки ленты по нему."""
import pytest

from core.database import VacancyRepository
from core.matching import compute_match_score

RESUME = "Опыт: Python, pytest, Selenium, REST Assured, SQL. QA automation engineer."


def test_high_match_full_overlap():
    vac = {"title": "QA Automation Engineer", "skills": "Python, Selenium, SQL"}
    assert compute_match_score(RESUME, vac) >= 80


def test_low_match_unrelated():
    vac = {"title": "Бухгалтер", "skills": "1С, Бухучёт, Налоги"}
    assert compute_match_score(RESUME, vac) <= 10


def test_zero_without_resume():
    vac = {"title": "QA Engineer", "skills": "Python, SQL"}
    assert compute_match_score("", vac) == 0


def test_partial_skills():
    vac = {"title": "QA Engineer", "skills": "Python, Selenium, Docker, Kafka"}
    # 2 из 4 навыков в резюме → средний балл
    score = compute_match_score(RESUME, vac)
    assert 30 <= score <= 70


def test_no_skills_uses_title():
    vac = {"title": "Python Developer", "skills": "Не указаны"}
    score = compute_match_score(RESUME, vac)
    assert 40 <= score <= 60   # python есть, developer нет → ~50


@pytest.fixture
def repo(tmp_path):
    return VacancyRepository(db_path=str(tmp_path / "m.db"))


def _vac(vid, score):
    return {
        "id": vid, "title": "QA", "company": "ACME",
        "salary_min": None, "salary_max": None, "description": "",
        "skills": "", "status": "discovered", "match_score": score,
    }


def test_feed_sorted_by_match_desc_nulls_last(repo):
    repo.save_vacancies([_vac("1", 30), _vac("2", 90), _vac("3", None)])
    order = [v["id"] for v in repo.get_vacancies_filtered("all")]
    assert order == ["2", "1", "3"]


def test_update_match_score(repo):
    repo.save_vacancies([_vac("1", None)])
    repo.update_match_score("1", 77)
    assert repo.get_vacancy_by_id("1")["match_score"] == 77
