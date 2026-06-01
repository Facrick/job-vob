import json
import sqlite3
import logging
import csv
from typing import List, Optional

from core.models import VacancyStatus


class VacancyRepository:
    def __init__(self, db_path: str = "data/app.db"):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vacancies (
                    id TEXT PRIMARY KEY, title TEXT, company TEXT, salary_min REAL,
                    salary_max REAL, description TEXT, skills TEXT, status TEXT, notes TEXT
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cover_letters (
                    vacancy_id TEXT PRIMARY KEY, letter_text TEXT, recommendations TEXT,
                    FOREIGN KEY(vacancy_id) REFERENCES vacancies(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS mock_interviews (
                    vacancy_id TEXT PRIMARY KEY, history_json TEXT,
                    FOREIGN KEY(vacancy_id) REFERENCES vacancies(id)
                )
            """)
            conn.commit()

    def get_vacancy_by_id(self, vacancy_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_notes(self, vacancy_id: str, notes_text: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE vacancies SET notes = ? WHERE id = ?", (notes_text, vacancy_id)
            )
            conn.commit()

    def save_vacancies(self, vacancies: List[dict]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for v in vacancies:
                cursor.execute("""
                    INSERT INTO vacancies (id, title, company, salary_min, salary_max, description, skills, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title, company=excluded.company, salary_min=excluded.salary_min,
                        salary_max=excluded.salary_max, description=excluded.description, skills=excluded.skills
                """, (
                    v["id"], v.get("title"), v.get("company"), v.get("salary_min"),
                    v.get("salary_max"), v.get("description"), v.get("skills"),
                    v.get("status", VacancyStatus.DISCOVERED.value),
                ))
            conn.commit()

    def update_status(self, vacancy_id: str, status: str):
        # status может быть как str, так и VacancyStatus — str(...) приводит к чистому значению
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE vacancies SET status = ? WHERE id = ?", (str(status), vacancy_id)
            )
            conn.commit()

    def get_vacancies_filtered(self, status: str) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status == "all":
                cursor.execute("SELECT * FROM vacancies")
            else:
                cursor.execute("SELECT * FROM vacancies WHERE status = ?", (str(status),))
            return [dict(row) for row in cursor.fetchall()]

    def clear_discovered_vacancies(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM vacancies WHERE status = ?",
                (VacancyStatus.DISCOVERED.value,),
            )
            conn.commit()

    def save_cover_letter(self, vacancy_id: str, letter: str, recs: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO cover_letters VALUES (?, ?, ?)",
                (vacancy_id, letter, recs),
            )
            conn.commit()

    def get_cover_letter(self, vacancy_id: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cover_letters WHERE vacancy_id = ?", (vacancy_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_mock_interview(self, vacancy_id: str, history_list: list):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO mock_interviews VALUES (?, ?)",
                (vacancy_id, json.dumps(history_list)),
            )
            conn.commit()

    def get_mock_interview(self, vacancy_id: str) -> Optional[list]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT history_json FROM mock_interviews WHERE vacancy_id = ?",
                (vacancy_id,),
            )
            row = cursor.fetchone()
            return json.loads(row[0]) if row else None


class DataExporter:
    def __init__(self, repo: VacancyRepository):
        self.repo = repo

    def export_discovered_to_csv(self, file_path: str):
        try:
            vacs = self.repo.get_vacancies_filtered("all")
            with open(file_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["ID", "Company", "Title", "Salary Min", "Status", "Notes"])
                for v in vacs:
                    writer.writerow([
                        v["id"], v["company"], v["title"],
                        v["salary_min"], v["status"], v.get("notes", ""),
                    ])
            return True, f"Экспортировано {len(vacs)} вакансий в {file_path}"
        except Exception as e:
            return False, str(e)
