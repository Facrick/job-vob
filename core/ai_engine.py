import json
import logging
import os
import re
import time
from pathlib import Path

from groq import Groq
from pypdf import PdfReader

from core.config import AppConfig, PromptRepository


class ResumeEntity:
    def __init__(self, file_path: str = "resume.pdf"):
        self.file_path = Path(file_path)
        self._cached_text: str | None = None

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
            raise RuntimeError(f"Ошибка при чтении PDF: {e}") from e


class LetterAnalyzer:
    def __init__(self):
        self.config = AppConfig()
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY не найден в .env")
        self.client = Groq(api_key=self.api_key)
        self.model = self.config.get("llm_model")
        self.fallback_model = self.config.get("llm_fallback_model")
        self.analysis_model = self.config.get("llm_analysis_model")
        self.prompt_repo = PromptRepository()
        logging.info(
            f"[AI] Модель: {self.model} (резерв: {self.fallback_model})"
        )

    def _complete(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        *,
        json_mode: bool = True,
        max_tokens: int | None = None,
        max_retries: int = 3,
        model: str | None = None,
    ) -> str:
        """Запрос к Groq с ретраями и фолбэком на резервную модель.

        model — явная модель (напр. быстрая для анализа). Если не задана,
        используется основная, затем резервная. Возвращает content; бросает
        последнюю ошибку, только если упали все модели.
        """
        if model:
            models = [model]
        else:
            models = [self.model]
            if self.fallback_model and self.fallback_model != self.model:
                models.append(self.fallback_model)

        last_error: Exception | None = None
        for model in models:
            for attempt in range(max_retries):
                try:
                    completion = self.client.chat.completions.create(
                        messages=messages,
                        model=model,
                        temperature=temperature,
                        response_format={"type": "json_object"} if json_mode else None,
                        max_tokens=max_tokens,
                        timeout=60,
                    )
                    return completion.choices[0].message.content
                except Exception as e:
                    last_error = e
                    logging.warning(
                        f"[AI] {model}: попытка {attempt + 1}/{max_retries} не удалась: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
            if len(models) > 1:
                logging.warning(f"[AI] Переключаюсь на резервную модель после сбоя {model}")

        raise last_error if last_error else RuntimeError("Groq: неизвестная ошибка")

    def _call_groq_with_retry(
        self,
        messages: list[dict[str, str]],
        temperature: float,
    ) -> dict:
        return json.loads(self._complete(messages, temperature, json_mode=True))

    def generate_cover_letter(
        self, resume_text: str, title: str, company: str, description: str
    ) -> dict[str, object]:
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
    ) -> dict[str, str]:
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

    def analyze_vacancy(
        self, resume_text: str, title: str, company: str, description: str
    ) -> dict[str, object]:
        """ИИ-анализ вакансии: требования, стек, соответствие резюме, пробелы.

        Оптимизировано на скорость: быстрая модель, лимит выходных токенов и
        обрезка длинных входов (описание/резюме) — без потери сути.
        """
        system_prompt = self.prompt_repo.get_vacancy_analysis_instruction()
        user_prompt = (
            f"ВАКАНСИЯ: {title} в компании {company}\n"
            f"ОПИСАНИЕ ВАКАНСИИ:\n{description[:4000]}\n\n"
            f"РЕЗЮМЕ КАНДИДАТА:\n{(resume_text or '(резюме не предоставлено)')[:3000]}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages,
            self.config.get("llm_temperature_generation"),
            json_mode=True,
            max_tokens=700,
            model=self.analysis_model,
        )
        return json.loads(content)

    def generate_handbook_article(self, topic: str, context: str = "") -> dict[str, str]:
        """Генерирует раздел учебника по теме → {question, answer(HTML)}.

        Используется, когда нужного материала нет в учебнике: ИИ создаёт его,
        а пользователь проверяет/правит. Быстрая модель + лимит токенов.
        """
        system_prompt = self.prompt_repo.get_handbook_article_instruction()
        user_prompt = f"Тема: {topic}"
        if context:
            user_prompt += f"\nКонтекст (из вакансии): {context[:800]}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages, temperature=0.3, json_mode=True,
            max_tokens=1100, model=self.analysis_model,
        )
        data = json.loads(content)
        return {
            "question": (data.get("question") or topic).strip(),
            "answer": (data.get("answer") or "").strip(),
        }

    def revise_handbook_article(self, title: str, current_md: str, instructions: str = "") -> str:
        """Правит материал учебника по инструкциям пользователя → Markdown-текст."""
        system_prompt = self.prompt_repo.get_handbook_revise_instruction()
        ask = instructions.strip() or "Улучши текст: исправь ошибки, добавь пример, структурируй."
        user_prompt = (
            f"Тема: {title}\n\nТЕКУЩИЙ ТЕКСТ (Markdown):\n{current_md[:6000]}\n\n"
            f"ПОЖЕЛАНИЯ ПО ПРАВКАМ:\n{ask}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages, temperature=0.3, json_mode=False,
            max_tokens=1200, model=self.analysis_model,
        )
        return content.strip()

    # ── Форматы интервью ──────────────────────────────────────────────
    _INTERVIEW_FORMATS: dict[str, dict] = {
        "tech": {
            "label": "Техническое",
            "system": (
                "Ты — строгий Senior QA Lead в компании {company}. "
                "Проводишь техническое интервью на позицию «{title}». "
                "Требования:\n{description}\n\n"
                "Представься и задай ОДИН технический вопрос по стеку. Не пиши за кандидата."
            ),
            "eval_note": (
                "Оцени кандидата по пяти компетенциям технического интервью QA:\n"
                "1. Технические знания\n2. Методология тестирования\n"
                "3. Инструменты и стек\n4. Критическое мышление\n5. Глубина знаний"
            ),
        },
        "hr": {
            "label": "HR-скрининг",
            "system": (
                "Ты — профессиональный HR-менеджер в компании {company}. "
                "Проводишь скрининговое интервью кандидата на позицию «{title}». "
                "Фокус: мотивация, soft skills, карьерные цели, culture fit, командная работа. "
                "Задавай поведенческие вопросы. Никаких технических вопросов. "
                "Представься, объясни формат и задай первый вопрос."
            ),
            "eval_note": (
                "Оцени кандидата по пяти HR-компетенциям:\n"
                "1. Коммуникация\n2. Мотивация\n"
                "3. Cultural Fit\n4. Карьерные цели\n5. Эмоциональный интеллект"
            ),
        },
        "system_design": {
            "label": "System Design",
            "system": (
                "Ты — Senior QA Architect в компании {company}. "
                "Проводишь System Design интервью на позицию «{title}». "
                "Описание роли:\n{description}\n\n"
                "Попроси кандидата спроектировать систему тестирования для ключевого сервиса компании. "
                "Оценивай: структурность подхода, полноту тест-плана, выбор инструментов, понимание рисков. "
                "Представься, опиши задачу и жди ответа. Задавай уточняющие вопросы по ходу."
            ),
            "eval_note": (
                "Оцени кандидата по пяти компетенциям System Design интервью:\n"
                "1. Системное мышление\n2. Полнота тест-плана\n"
                "3. Инструменты и архитектура\n4. Управление рисками\n5. Структурность"
            ),
        },
        "behavioral": {
            "label": "Поведенческое (STAR)",
            "system": (
                "Ты — Senior QA Lead в компании {company}. "
                "Проводишь поведенческое интервью на позицию «{title}» по методике STAR. "
                "После каждого ответа давай краткую оценку структуры (Situation/Task/Action/Result) "
                "и задавай следующий вопрос. "
                "Темы: сложные баги, конфликты в команде, дедлайны, провальный релиз, обучение новому. "
                "Представься и начни с первого STAR-вопроса."
            ),
            "eval_note": (
                "Оцени кандидата по пяти поведенческим компетенциям (методика STAR):\n"
                "1. Структура ответов (STAR)\n2. Командная работа\n"
                "3. Управление конфликтами\n4. Обучаемость\n5. Ответственность за результат"
            ),
        },
    }

    @classmethod
    def get_interview_system_prompt(cls, fmt: str, company: str, title: str, description: str) -> str:
        tpl = cls._INTERVIEW_FORMATS.get(fmt, cls._INTERVIEW_FORMATS["tech"])["system"]
        return tpl.format(company=company, title=title, description=description[:2000])

    def generate_mock_reply(self, messages_history: list[dict[str, str]]) -> str:
        try:
            content = self._complete(
                messages_history, temperature=0.5, json_mode=False, max_tokens=800
            )
            return content.strip()
        except Exception as e:
            logging.error(f"Ошибка в mock-интервью: {e}")
            return "Извините, произошла техническая ошибка."

    def evaluate_mock_interview(
        self, history: list[dict], fmt: str, title: str, company: str
    ) -> dict:
        """Оценивает сессию mock-интервью → JSON с компетенциями, сильными сторонами и рекомендацией."""
        fmt_info = self._INTERVIEW_FORMATS.get(fmt, self._INTERVIEW_FORMATS["tech"])
        eval_note = fmt_info["eval_note"]
        # Фильтруем системные сообщения и берём только диалог
        dialog = "\n".join(
            f"[{'Интервьюер' if m['role'] == 'assistant' else 'Кандидат'}]: {m['content']}"
            for m in history if m["role"] in ("assistant", "user")
        )
        system_prompt = (
            f"Ты — объективный эксперт по оценке кандидатов. "
            f"Проанализируй запись интервью на позицию «{title}» в компании {company}.\n\n"
            f"{eval_note}\n\n"
            "Верни СТРОГО JSON-объект:\n"
            "{\n"
            '  "summary": "2-3 предложения: общее впечатление о кандидате",\n'
            '  "competencies": [\n'
            '    {"name": "Название", "score": 8, "comment": "1 предложение"}, ...\n'
            "  ],\n"
            '  "strengths": ["сильная сторона 1", "сильная сторона 2"],\n'
            '  "improvements": ["что улучшить 1", "что улучшить 2"],\n'
            '  "recommendation": "Рекомендую к следующему этапу / Нужна дополнительная подготовка / Не рекомендую"\n'
            "}\n"
            "score — целое число от 1 до 10. Будь честным и конкретным."
        )
        content = self._complete(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": f"ЗАПИСЬ ИНТЕРВЬЮ:\n{dialog[:6000]}"}],
            temperature=0.2, json_mode=True, max_tokens=900, model=self.analysis_model,
        )
        return json.loads(content)
