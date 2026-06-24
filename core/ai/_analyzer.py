"""LetterAnalyzer — AI-движок: письма, анализ вакансий, учебник, упражнения."""
import json
import logging

from core.ai._base import BaseAIClient
from core.prompts import PromptRepository


class LetterAnalyzer(BaseAIClient):
    def __init__(self):
        super().__init__(log_prefix="[AI]")
        self.prompt_repo = PromptRepository()

    # Письмо ~900-1400 символов → с запасом на JSON-обёртку хватает ~1200 токенов.
    # Кап ускоряет ответ и не даёт модели «растекаться».
    _LETTER_MAX_TOKENS = 1200

    def _call_groq_with_retry(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        *,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        content = self._complete(
            messages, temperature, json_mode=True,
            model=model, max_tokens=max_tokens,
        )
        return self._parse_json_safe(
            content, fallback={"letter": "", "recommendations": []}
        )

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
            messages, self.config.get("llm_temperature_generation"),
            model=self.analysis_model,
            max_tokens=self._LETTER_MAX_TOKENS,
        )

    def adjust_letter(
        self, old_letter: str, feedback: str, title: str, description: str
    ) -> dict[str, str]:
        system_prompt = self.prompt_repo.get_adjustment_instruction()
        # Описание режем: при правке важно письмо и пожелания, а не весь текст
        # вакансии — длинный промпт замедляет ответ без пользы для редактуры.
        user_prompt = (
            f"Вакансия: {title}\nОписание: {description[:1500]}\n\n"
            f"Текущее письмо:\n{old_letter}\n\nПожелания по правкам: {feedback}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        # Правка письма — лёгкая задача редактуры: гоним на быстрой analysis-модели
        # с капом токенов. Это и есть главная причина прежней медлительности.
        return self._call_groq_with_retry(
            messages, self.config.get("llm_temperature_adjustment"),
            model=self.analysis_model,
            max_tokens=self._LETTER_MAX_TOKENS,
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
        return self._parse_json_safe(content)

    def score_cover_letter(
        self, letter_text: str, title: str, company: str, description: str
    ) -> dict:
        """Оценивает сопроводительное письмо по 4 критериям."""
        system_prompt = (
            "Ты — опытный HR-специалист. Оцени сопроводительное письмо кандидата "
            "по четырём критериям и дай краткий комментарий на русском языке.\n\n"
            "Критерии (каждый от 0 до 10):\n"
            "1. Релевантность — насколько письмо соответствует конкретной вакансии\n"
            "2. Конкретность — есть ли реальные примеры, достижения, цифры\n"
            "3. Структура — оптимальный объём (900-1400 символов), логика, читаемость\n"
            "4. Тон и стиль — профессиональный, уверенный, без шаблонных фраз\n\n"
            "score (0-100) = сумма баллов по критериям × 2.5 (итого максимум 100).\n\n"
            "Верни СТРОГО JSON (никакого Markdown вокруг):\n"
            '{"score": <целое 0-100>, '
            '"criteria": ['
            '{"name": "Релевантность", "score": <0-10>, "max": 10, "comment": "..."},'
            '{"name": "Конкретность", "score": <0-10>, "max": 10, "comment": "..."},'
            '{"name": "Структура", "score": <0-10>, "max": 10, "comment": "..."},'
            '{"name": "Тон и стиль", "score": <0-10>, "max": 10, "comment": "..."}'
            '], '
            '"summary": "Итоговый вывод 1-2 предложения."}'
        )
        user_prompt = (
            f"Вакансия: {title} в компании {company}\n"
            f"Описание вакансии:\n{description[:1500]}\n\n"
            f"СОПРОВОДИТЕЛЬНОЕ ПИСЬМО:\n{letter_text[:2000]}"
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        content = self._complete(
            messages, temperature=0.1, json_mode=True,
            max_tokens=700, model=self.analysis_model,
        )
        data = self._parse_json_safe(content, fallback={"score": 0, "criteria": [], "summary": ""})
        try:
            score = max(0, min(100, int(data.get("score", 0))))
            criteria = data.get("criteria") or []
            # Пересчитываем score из критериев если он 0 (модель иногда забывает)
            if score == 0 and criteria:
                total = sum(int(c.get("score", 0)) for c in criteria)
                score = min(100, int(total * 2.5))
            return {
                "score": score,
                "criteria": criteria,
                "summary": data.get("summary", ""),
            }
        except (ValueError, TypeError) as e:
            logging.error(f"[AI Score] Ошибка нормализации оценки: {e}")
            return {"score": 0, "criteria": [], "summary": "Ошибка оценки."}

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
        data = self._parse_json_safe(content)
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
