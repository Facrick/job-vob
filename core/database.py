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

    def init_db(self) -> None:
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
            if "created_at" not in columns:
                cursor.execute("ALTER TABLE vacancies ADD COLUMN created_at TEXT")

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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cover_letter_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vacancy_id TEXT NOT NULL,
                    letter_text TEXT,
                    recommendations TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(vacancy_id) REFERENCES vacancies(id)
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS salary_stats (
                    query TEXT PRIMARY KEY,
                    collected_at TEXT NOT NULL,
                    resume_count INTEGER NOT NULL,
                    data_json TEXT NOT NULL
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

    def update_details(self, vacancy_id: str, details: dict) -> None:
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

    def save_vacancies(self, vacancies: list[dict]) -> None:
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for v in vacancies:
                cursor.execute("""
                    INSERT INTO vacancies
                        (id, title, company, salary_min, salary_max, description, skills,
                         status, match_score, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title, company=excluded.company,
                        salary_min=excluded.salary_min, salary_max=excluded.salary_max,
                        description=excluded.description, skills=excluded.skills,
                        match_score=excluded.match_score
                """, (
                    v["id"], v.get("title"), v.get("company"), v.get("salary_min"),
                    v.get("salary_max"), v.get("description"), v.get("skills"),
                    v.get("status", VacancyStatus.DISCOVERED.value), v.get("match_score"),
                    now,
                ))
            conn.commit()

    def update_notes(self, vacancy_id: str, notes_text: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE vacancies SET notes = ? WHERE id = ?", (notes_text, vacancy_id)
            )
            conn.commit()

    def update_match_score(self, vacancy_id: str, score: int | None) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE vacancies SET match_score = ? WHERE id = ?", (score, vacancy_id)
            )
            conn.commit()

    def update_status(self, vacancy_id: str, status: str) -> None:
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

    def clear_discovered_vacancies(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM vacancies WHERE status = ?",
                (VacancyStatus.DISCOVERED.value,),
            )
            conn.commit()

    _MAX_LETTER_VERSIONS = 5

    def save_cover_letter(self, vacancy_id: str, letter: str, recs: str) -> None:
        from datetime import datetime
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO cover_letters VALUES (?, ?, ?)",
                (vacancy_id, letter, recs),
            )
            # Сохраняем в историю версий
            cursor.execute(
                "INSERT INTO cover_letter_history (vacancy_id, letter_text, recommendations, created_at)"
                " VALUES (?, ?, ?, ?)",
                (vacancy_id, letter, recs, datetime.now().isoformat(timespec="seconds")),
            )
            # Удаляем старые версии, оставляем последние _MAX_LETTER_VERSIONS
            cursor.execute(
                "DELETE FROM cover_letter_history WHERE vacancy_id = ? AND id NOT IN ("
                "  SELECT id FROM cover_letter_history WHERE vacancy_id = ?"
                "  ORDER BY id DESC LIMIT ?"
                ")",
                (vacancy_id, vacancy_id, self._MAX_LETTER_VERSIONS),
            )
            conn.commit()

    def get_activity_by_date(self, days: int = 30) -> list[dict]:
        """Активность по дням: сколько вакансий добавлено за последние N дней.

        Возвращает список {"date": "YYYY-MM-DD", "total": N, "applied": N,
        "interview": N, "offer": N} отсортированный от старых к новым.
        Вакансии без created_at исключаются.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    SUBSTR(created_at, 1, 10)   AS date,
                    COUNT(*)                     AS total,
                    SUM(status = 'applied')      AS applied,
                    SUM(status = 'interview')    AS interview,
                    SUM(status = 'offer')        AS offer
                FROM vacancies
                WHERE created_at IS NOT NULL
                  AND DATE(created_at) >= DATE('now', ? || ' days')
                GROUP BY SUBSTR(created_at, 1, 10)
                ORDER BY date ASC
            """, (f"-{days}",))
            return [dict(row) for row in cursor.fetchall()]

    def get_letter_history(self, vacancy_id: str) -> list[dict]:
        """Возвращает историю версий письма (новые первыми), до _MAX_LETTER_VERSIONS."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, letter_text, recommendations, created_at"
                " FROM cover_letter_history WHERE vacancy_id = ?"
                " ORDER BY id DESC",
                (vacancy_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_cover_letter(self, vacancy_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM cover_letters WHERE vacancy_id = ?", (vacancy_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def save_mock_interview(self, vacancy_id: str, history_list: list) -> None:
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

    def save_salary_stats(self, query: str, stats: dict) -> None:
        from datetime import datetime
        with sqlite3.connect(self.db_path) as conn:
            conn.cursor().execute(
                "INSERT OR REPLACE INTO salary_stats (query, collected_at, resume_count, data_json)"
                " VALUES (?, ?, ?, ?)",
                (
                    query.lower().strip(),
                    datetime.now().isoformat(timespec="seconds"),
                    stats.get("count", 0),
                    json.dumps(stats, ensure_ascii=False),
                ),
            )
            conn.commit()

    def get_salary_stats(self, query: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data_json, collected_at FROM salary_stats WHERE query = ?",
                (query.lower().strip(),),
            )
            row = cursor.fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            data["collected_at"] = row[1]
            return data

    def list_salary_stats(self) -> list[dict]:
        """Возвращает список всех сохранённых снимков (query, collected_at, count)."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT query, collected_at, resume_count FROM salary_stats"
                " ORDER BY collected_at DESC"
            )
            return [
                {"query": r[0], "collected_at": r[1], "resume_count": r[2]}
                for r in cursor.fetchall()
            ]


class DataExporter:
    def __init__(self, repo: VacancyRepository):
        self.repo = repo

    def export_discovered_to_csv(self, file_path: str) -> tuple[bool, str]:
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
