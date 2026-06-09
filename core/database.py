import csv
import json
import sqlite3

from core.models import VacancyStatus
from core.paths import user_path


class VacancyRepository:
    def __init__(self, db_path: str | None = None):
        # По умолчанию — записываемый путь (dev: <проект>/data, frozen: рядом с .exe)
        self.db_path = str(db_path) if db_path else str(user_path("data/app.db"))
        self.init_db()

    def init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vacancies (
                    id TEXT PRIMARY KEY, title TEXT, company TEXT, salary_min REAL,
                    salary_max REAL, description TEXT, skills TEXT, status TEXT, notes TEXT,
                    hr_name TEXT, contacts TEXT, interview_date TEXT, match_score INTEGER
                )
            """)

            # Лёгкая миграция: добавляем новые колонки, если их нет
            cursor.execute("PRAGMA table_info(vacancies)")
            columns = {row[1] for row in cursor.fetchall()}
            if "match_score" not in columns:
                cursor.execute("ALTER TABLE vacancies ADD COLUMN match_score INTEGER")
            if "hr_name" not in columns:
                cursor.execute("ALTER TABLE vacancies ADD COLUMN hr_name TEXT")
            if "contacts" not in columns:
                cursor.execute("ALTER TABLE vacancies ADD COLUMN contacts TEXT")
            if "interview_date" not in columns:
                cursor.execute("ALTER TABLE vacancies ADD COLUMN interview_date TEXT")

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

    def get_vacancy_by_id(self, vacancy_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vacancies WHERE id = ?", (vacancy_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_details(self, vacancy_id: str, details: dict):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE vacancies
                SET hr_name = ?, contacts = ?, interview_date = ?, notes = ?
                WHERE id = ?
            """, (
                details.get("hr_name"),
                details.get("contacts"),
                details.get("interview_date"),
                details.get("notes"),
                vacancy_id
            ))
            conn.commit()

    def save_vacancies(self, vacancies: list[dict]):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for v in vacancies:
                cursor.execute("""
                    INSERT INTO vacancies
                        (id, title, company, salary_min, salary_max, description, skills, status, match_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title, company=excluded.company, salary_min=excluded.salary_min,
                        salary_max=excluded.salary_max, description=excluded.description,
                        skills=excluded.skills, match_score=excluded.match_score
                """, (
                    v["id"], v.get("title"), v.get("company"), v.get("salary_min"),
                    v.get("salary_max"), v.get("description"), v.get("skills"),
                    v.get("status", VacancyStatus.DISCOVERED.value), v.get("match_score"),
                ))
            conn.commit()

    def update_notes(self, vacancy_id: str, notes_text: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE vacancies SET notes = ? WHERE id = ?", (notes_text, vacancy_id)
            )
            conn.commit()

    def update_match_score(self, vacancy_id: str, score: int | None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE vacancies SET match_score = ? WHERE id = ?", (score, vacancy_id)
            )
            conn.commit()

    def update_status(self, vacancy_id: str, status: str):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE vacancies SET status = ? WHERE id = ?", (str(status), vacancy_id)
            )
            conn.commit()

    def get_vacancies_filtered(self, status: str) -> list[dict]:
        order = "ORDER BY match_score IS NULL, match_score DESC, id"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if status == "all":
                cursor.execute(f"SELECT * FROM vacancies {order}")
            else:
                cursor.execute(
                    f"SELECT * FROM vacancies WHERE status = ? {order}", (str(status),)
                )
            return [dict(row) for row in cursor.fetchall()]

    def delete_vacancy(self, vacancy_id: str) -> None:
        """Полностью удаляет вакансию и все связанные данные (письма, интервью)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cover_letters WHERE vacancy_id = ?", (vacancy_id,))
            cursor.execute("DELETE FROM mock_interviews WHERE vacancy_id = ?", (vacancy_id,))
            cursor.execute("DELETE FROM vacancies WHERE id = ?", (vacancy_id,))
            conn.commit()

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

    def count_cover_letters(self) -> int:
        """Сколько вакансий имеют сохранённое сопроводительное письмо."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM cover_letters "
                "WHERE letter_text IS NOT NULL AND TRIM(letter_text) <> ''"
            )
            return int(cursor.fetchone()[0])

    def get_cover_letter(self, vacancy_id: str) -> dict | None:
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

    def get_mock_interview(self, vacancy_id: str) -> list | None:
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
                writer.writerow(["ID", "Company", "Title", "Salary Min", "Status", "Notes", "HR Name", "Contacts", "Interview Date"])
                for v in vacs:
                    writer.writerow([
                        v["id"], v["company"], v["title"],
                        v["salary_min"], v["status"], v.get("notes", ""),
                        v.get("hr_name", ""), v.get("contacts", ""), v.get("interview_date", "")
                    ])
            return True, f"Экспортировано {len(vacs)} вакансий в {file_path}"
        except Exception as e:
            return False, str(e)
