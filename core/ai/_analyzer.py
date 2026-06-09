"""LetterAnalyzer — AI-движок на базе Groq: письма, анализ вакансий, учебник, упражнения."""
import json
import logging
import os
import time

from groq import Groq

from core.config import AppConfig
from core.prompts import PromptRepository


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
        logging.info(f"[AI] Модель: {self.model} (резерв: {self.fallback_model})")

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
        """Запрос к Groq с ретраями и фолбэком на резервную модель."""
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
                        time.sleep(2**attempt)
            if len(models) > 1:
                logging.warning(
                    f"[AI] Переключаюсь на резервную модель после сбоя {model}"
                )

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
        """ИИ-анализ вакансии: требования, стек, соответствие резюме, пробелы."""
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

    def generate_handbook_article(
        self, topic: str, context: str = "", persona: str = ""
    ) -> dict[str, str]:
        """Генерирует раздел учебника по теме → {question, answer(HTML)}."""
        system_prompt = self.prompt_repo.get_handbook_article_instruction()
        if persona:
            system_prompt += (
                f"\n\nНаправление учебника: {persona}. "
                "Пиши материал и примеры именно под это направление."
            )
        user_prompt = f"Тема: {topic}"
        if context:
            user_prompt += f"\nКонтекст (из вакансии): {context[:800]}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages,
            temperature=0.3,
            json_mode=True,
            max_tokens=1100,
            model=self.analysis_model,
        )
        data = json.loads(content)
        return {
            "question": (data.get("question") or topic).strip(),
            "answer": (data.get("answer") or "").strip(),
        }

    def revise_handbook_article(
        self, title: str, current_md: str, instructions: str = ""
    ) -> str:
        """Правит материал учебника по инструкциям пользователя → Markdown-текст."""
        system_prompt = self.prompt_repo.get_handbook_revise_instruction()
        ask = (
            instructions.strip()
            or "Улучши текст: исправь ошибки, добавь пример, структурируй."
        )
        user_prompt = (
            f"Тема: {title}\n\nТЕКУЩИЙ ТЕКСТ (Markdown):\n{current_md[:6000]}\n\n"
            f"ПОЖЕЛАНИЯ ПО ПРАВКАМ:\n{ask}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages,
            temperature=0.3,
            json_mode=False,
            max_tokens=1200,
            model=self.analysis_model,
        )
        return content.strip()

    def generate_quiz_question(
        self, topic_title: str, answer_content: str, persona: str = ""
    ) -> str:
        """Генерирует реальный вопрос для собеседования по теме учебника."""
        system_prompt = self.prompt_repo.get_quiz_question_instruction()
        if persona:
            system_prompt += f"\nНаправление собеседования: {persona}."
        user_prompt = (
            f"Тема: {topic_title}\n\n"
            f"Краткое содержание темы:\n{answer_content[:1500]}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages,
            temperature=0.4,
            json_mode=True,
            max_tokens=150,
            model=self.analysis_model,
        )
        try:
            return json.loads(content).get("question", topic_title)
        except (json.JSONDecodeError, AttributeError):
            return topic_title

    def evaluate_quiz_answer(
        self, question: str, reference_answer: str, user_answer: str
    ) -> dict[str, str]:
        """Оценивает ответ пользователя в квизе по сравнению с эталонным."""
        system_prompt = self.prompt_repo.get_quiz_evaluation_instruction()
        user_prompt = (
            f"ВОПРОС:\n{question}\n\n"
            f"ЭТАЛОННЫЙ ОТВЕТ:\n{reference_answer[:3000]}\n\n"
            f"ОТВЕТ КАНДИДАТА:\n{user_answer[:2000]}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages,
            temperature=0.1,
            json_mode=True,
            max_tokens=400,
            model=self.analysis_model,
        )
        try:
            data = json.loads(content)
            if "evaluation" not in data or "feedback" not in data:
                raise ValueError("Ответ ИИ не содержит ключей evaluation/feedback")
            return data
        except (json.JSONDecodeError, ValueError) as e:
            logging.error(f"[AI Quiz] Ошибка парсинга ответа ИИ: {e}. Ответ: {content}")
            return {
                "evaluation": "Error",
                "feedback": "Произошла ошибка при анализе ответа. Попробуйте снова.",
            }

    def generate_exercise(
        self, topic_title: str, answer_content: str, persona: str = ""
    ) -> dict:
        """Генерирует практическое задание по теме: {task, reference, rubric}."""
        system_prompt = self.prompt_repo.get_exercise_generation_instruction()
        if persona:
            system_prompt += f"\nНаправление: {persona}."
        user_prompt = (
            f"Тема: {topic_title}\n\n"
            f"Содержание темы:\n{answer_content[:2000]}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages, temperature=0.6, json_mode=True,
            max_tokens=900, model=self.analysis_model,
        )
        try:
            data = json.loads(content)
            if not data.get("task"):
                raise ValueError("нет ключа task")
            return {
                "task": data.get("task", ""),
                "reference": data.get("reference", ""),
                "rubric": data.get("rubric", ""),
            }
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            logging.error(f"[AI Exercise] Ошибка генерации: {e}. Ответ: {content}")
            return {}

    def validate_exercise(
        self, task: str, topic_title: str, persona: str = ""
    ) -> dict:
        """Role A: контролёр проверяет КОРРЕКТНОСТЬ задания (не решает его)."""
        system_prompt = self.prompt_repo.get_exercise_validation_instruction()
        if persona:
            system_prompt += f"\nНаправление: {persona}."
        user_prompt = f"Тема: {topic_title}\n\nЧЕРНОВИК ЗАДАНИЯ:\n{task[:2000]}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        try:
            content = self._complete(
                messages, temperature=0.0, json_mode=True,
                max_tokens=400, model=self.analysis_model,
            )
            data = json.loads(content)
            return {
                "valid": bool(data.get("valid", True)),
                "reason": data.get("reason", ""),
                "fixed_task": (data.get("fixed_task") or "").strip(),
            }
        except Exception as e:  # noqa: BLE001
            logging.warning(f"[AI Exercise] Контролёр недоступен, пропускаю: {e}")
            return {"valid": True, "reason": "", "fixed_task": ""}

    def generate_validated_exercise(
        self, topic_title: str, answer_content: str, persona: str = "",
        max_attempts: int = 2,
    ) -> dict:
        """Генерирует задание и прогоняет его через контролёра (Role A)."""
        last: dict = {}
        for attempt in range(max(1, max_attempts)):
            ex = self.generate_exercise(topic_title, answer_content, persona)
            if not ex or not ex.get("task"):
                continue
            last = ex
            verdict = self.validate_exercise(ex["task"], topic_title, persona)
            if verdict.get("valid"):
                return ex
            fixed = verdict.get("fixed_task")
            if fixed:
                ex = {**ex, "task": fixed}
                return ex
            logging.info(
                f"[AI Exercise] Контролёр отклонил задание "
                f"(попытка {attempt + 1}): {verdict.get('reason')}"
            )
        return last

    def grade_exercise(
        self, task: str, reference: str, rubric: str, user_answer: str
    ) -> dict:
        """Оценивает ответ ученика по скрытому эталону и критериям."""
        system_prompt = self.prompt_repo.get_exercise_grading_instruction()
        user_prompt = (
            f"ЗАДАНИЕ:\n{task}\n\n"
            f"ЭТАЛОННЫЙ ОТВЕТ:\n{reference[:3000]}\n\n"
            f"КРИТЕРИИ:\n{rubric[:1500]}\n\n"
            f"ОТВЕТ УЧЕНИКА:\n{user_answer[:3000]}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages, temperature=0.1, json_mode=True,
            max_tokens=700, model=self.analysis_model,
        )
        try:
            data = json.loads(content)
            score = int(data.get("score", 0))
            return {
                "score": max(0, min(100, score)),
                "verdict": data.get("verdict", ""),
                "correct": data.get("correct", []) or [],
                "missing": data.get("missing", []) or [],
                "advice": data.get("advice", ""),
            }
        except (json.JSONDecodeError, ValueError, TypeError, AttributeError) as e:
            logging.error(f"[AI Exercise] Ошибка оценки: {e}. Ответ: {content}")
            return {
                "score": 0, "verdict": "Ошибка",
                "correct": [], "missing": [],
                "advice": "Не удалось оценить ответ. Попробуйте снова.",
            }
