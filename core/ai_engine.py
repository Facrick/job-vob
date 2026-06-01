import os
import re
import json
import time
import logging
from typing import Dict, List, Optional
from pathlib import Path

from pypdf import PdfReader
from groq import Groq

from core.config import AppConfig, PromptRepository
from core.utils import extract_salary_from_resume


class ResumeEntity:
    def __init__(self, file_path: str = "resume.pdf"):
        self.file_path = Path(file_path)
        self._cached_text: Optional[str] = None

    def extract_text(self) -> str:
        if self._cached_text:
            return self._cached_text
        if not self.file_path.exists():
            raise FileNotFoundError(f"Файл {self.file_path} не найден.")
        try:
            reader = PdfReader(self.file_path)
            text = "\n".join(
                page.extract_text() for page in reader.pages if page.extract_text()
            )
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n\s*\n", "\n", text).strip()
            self._cached_text = text
            return text
        except Exception as e:
            raise RuntimeError(f"Ошибка при чтении PDF: {e}")

    def extract_salary(self) -> int:
        """Извлекает ожидаемую зарплату; при неудаче — дефолт из конфига."""
        text = self.extract_text()
        salary = extract_salary_from_resume(text)
        if salary is not None:
            return salary

        default_salary = AppConfig().get("default_salary")
        logging.warning(f"Не удалось извлечь зарплату, использую дефолт: {default_salary}")
        return default_salary


class LetterAnalyzer:
    def __init__(self):
        self.config = AppConfig()
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY не найден в .env")
        self.client = Groq(api_key=self.api_key)
        self.model = self.config.get("llm_model")
        self.prompt_repo = PromptRepository()
        logging.info(f"[AI] Инициализирован с моделью: {self.model}")

    def _call_groq_with_retry(
        self,
        messages: List[Dict[str, str]],
        temperature: float,
        response_format: Optional[Dict] = None,
        max_retries: int = 3,
    ) -> Dict:
        for attempt in range(max_retries):
            try:
                completion = self.client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    temperature=temperature,
                    response_format=response_format or {"type": "json_object"},
                    timeout=60,
                )
                return json.loads(completion.choices[0].message.content)
            except Exception as e:
                logging.warning(f"Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    raise

    def generate_cover_letter(
        self, resume_text: str, title: str, company: str, description: str
    ) -> Dict[str, object]:
        system_prompt = self.prompt_repo.get_cover_letter_instruction()
        user_prompt = (
            f"ДАННЫЕ ДЛЯ СЛИЧЕНИЯ:\nКомпания: {company}\nВакансия: {title}\n"
            f"Описание вакансии:\n{description}\n\nТЕКСТ РЕЗЮМЕ КАНДИДАТА:\n{resume_text}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._call_groq_with_retry(
            messages, self.config.get("llm_temperature_generation")
        )

    def adjust_letter(
        self, old_letter: str, feedback: str, title: str, description: str
    ) -> Dict[str, str]:
        system_prompt = self.prompt_repo.get_adjustment_instruction()
        user_prompt = (
            f"Вакансия: {title}\nОписание: {description}\n\n"
            f"Текущее письмо:\n{old_letter}\n\nПожелания по правкам: {feedback}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        return self._call_groq_with_retry(
            messages, self.config.get("llm_temperature_adjustment")
        )

    def generate_mock_reply(self, messages_history: List[Dict[str, str]]) -> str:
        try:
            completion = self.client.chat.completions.create(
                messages=messages_history,
                model=self.model,
                temperature=0.5,
                max_tokens=800,
                timeout=45,
            )
            return completion.choices[0].message.content.strip()
        except Exception as e:
            logging.error(f"Ошибка в mock-интервью: {e}")
            return "Извините, произошла техническая ошибка."
