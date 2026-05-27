import os
import sqlite3
import logging
import re
import json
from logging.handlers import RotatingFileHandler
from pypdf import PdfReader
from parser import HHParser
from analyzer import CoverLetterGenerator

os.makedirs("logs", exist_ok=True)
logger = logging.getLogger()
logger.setLevel(logging.INFO)

file_handler = RotatingFileHandler("logs/bot_activity.log", maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(filename)s:%(lineno)d - %(message)s')
file_handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(file_handler)


def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/processed_vacancies.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS vacancies (
            id TEXT PRIMARY KEY, title TEXT, company TEXT, 
            salary_min REAL, salary_max REAL, description TEXT, status TEXT DEFAULT 'discovered'
        )
    """)
    conn.commit()
    return conn


def run_scout_process(keyword, exclude, experience, schedule, area, proxy_url=None):
    logging.info(f"Сканирование рынка по запросу: {keyword}")
    parser = HHParser(proxy_url=proxy_url if proxy_url.strip() else None)
    vacancies = parser.fetch_vacancies(text=keyword, period=1, area=area, experience=experience, schedule=schedule)

    conn = init_db()
    cursor = conn.cursor()
    new_counter = 0

    for v in vacancies:
        v_id = v.get("id")
        cursor.execute("SELECT 1 FROM vacancies WHERE id = ?", (str(v_id),))
        if cursor.fetchone():
            continue

        data = parser.get_vacancy_details(v_id)
        if not data:
            continue

        try:
            cursor.execute(
                "INSERT OR IGNORE INTO vacancies VALUES (?, ?, ?, ?, ?, ?, 'discovered')",
                (str(v_id), v.get("name"), data.get("company_name", "Не указана"), data.get("salary_min"),
                 data.get("salary_max"), data.get("description", ""))
            )
            new_counter += 1
        except Exception as e:
            logging.error(f"Ошибка сохранения {v_id}: {e}")
            continue

    conn.commit()
    conn.close()
    logging.info(f"Добавлено новых позиций: {new_counter}")


def run_generation_process(v_id, feedback_text="", proxy_url=None):
    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("SELECT title, company, description FROM vacancies WHERE id = ?", (str(v_id),))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "Вакансия не найдена."
    v_title, v_company, v_description = row
    conn.close()

    resume_text = ""
    if os.path.exists("resume.pdf"):
        try:
            logging.info("Извлекаю данные из resume.pdf...")
            reader = PdfReader("resume.pdf")
            resume_text = "\n".join([p.extract_text() for p in reader.pages if p.extract_text()])
            resume_text = re.sub(r'[ \t]+', ' ', resume_text)
            resume_text = re.sub(r'\n\s*\n', '\n', resume_text).strip()
        except Exception as e:
            return False, f"Ошибка чтения PDF: {e}"
    elif os.path.exists("resume.txt"):
        with open("resume.txt", "r", encoding="utf-8") as f:
            resume_text = f.read()

    if not resume_text.strip():
        return False, "В корне проекта не найден или пуст файл resume.pdf!"

    generator = CoverLetterGenerator()
    clean_company = re.sub(r'[\\/*?:"<>|]', "", v_company).strip().replace(' ', '_')
    clean_title = re.sub(r'[\\/*?:"<>|]', "", v_title).strip().replace(' ', '_')
    cover_filename = f"covers/[{clean_company}]_{clean_title}_сопроводительное.txt"

    FILE_SEPARATOR = "\n\n===SYSTEM_RECOMMENDATIONS_SPLIT_MARKER===\n\n"

    if feedback_text.strip() and os.path.exists(cover_filename):
        with open(cover_filename, "r", encoding="utf-8") as f:
            old_content = f.read()

        parts_letter = old_content.split(FILE_SEPARATOR)
        old_letter_body = parts_letter[0].split("==================================================")[-1].strip()
        old_recs = parts_letter[1].strip() if len(parts_letter) > 1 else "Повторите ключевой стек вакансии."

        json_output = generator.regenerate_with_feedback(old_letter_body, feedback_text, v_title, v_description)
        try:
            parsed_json = json.loads(json_output)
            new_letter = parsed_json.get("letter", json_output).strip()
        except Exception:
            new_letter = json_output.strip()

        result_text = f"{new_letter}{FILE_SEPARATOR}{old_recs}"
    else:
        raw_json_output = generator.generate(resume_text, v_title, v_company, v_description)

        try:
            parsed_json = json.loads(raw_json_output)
            letter_part = parsed_json.get("letter", "").strip()
            recs_list = parsed_json.get("recommendations", [])

            if isinstance(recs_list, list):
                recs_part = "\n".join([f"• {item}" for item in recs_list])
            else:
                recs_part = str(recs_list)
        except Exception as e:
            logging.error(f"Ошибка разбора JSON-пакета: {e}")
            letter_part = raw_json_output
            recs_part = "Повторите ключевой стек автоматизации, указанный в описании вакансии."

        result_text = f"{letter_part}{FILE_SEPARATOR}{recs_part}"

    os.makedirs("covers", exist_ok=True)
    meta_header = f"КОМПАНИЯ: {v_company}\nВАКАНСИЯ: {v_title}\nССЫЛКА НА ВАКАНСИЮ: https://hh.ru/vacancy/{v_id}\n==================================================\n"

    with open(cover_filename, "w", encoding="utf-8") as f:
        f.write(meta_header + result_text)

    conn = init_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE vacancies SET status = 'processed' WHERE id = ?", (str(v_id),))
    conn.commit()
    conn.close()
    return True, ""
