import json
import logging
import os
import time

from groq import Groq

from core.config import AppConfig


class MockInterviewEngine:
    def __init__(self):
        self.config = AppConfig()
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY не найден в .env")
        self.client = Groq(api_key=self.api_key)
        self.model = self.config.get("llm_model")
        self.fallback_model = self.config.get("llm_fallback_model")
        self.analysis_model = self.config.get("llm_analysis_model")
        logging.info(
            f"[AI-Interview] Модель: {self.model} (резерв: {self.fallback_model})"
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
        """Запрос к Groq с ретраями и фолбэком на резервную модель."""
        if model:
            models = [model]
        else:
            models = [self.model]
            if self.fallback_model and self.fallback_model != self.model:
                models.append(self.fallback_model)

        last_error: Exception | None = None
        for model_name in models:
            for attempt in range(max_retries):
                try:
                    completion = self.client.chat.completions.create(
                        messages=messages,
                        model=model_name,
                        temperature=temperature,
                        response_format={"type": "json_object"} if json_mode else None,
                        max_tokens=max_tokens,
                        timeout=60,
                    )
                    return completion.choices[0].message.content
                except Exception as e:
                    last_error = e
                    logging.warning(
                        f"[AI] {model_name}: попытка {attempt + 1}/{max_retries} не удалась: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
            if len(models) > 1:
                logging.warning(
                    f"[AI] Переключаюсь на резервную модель после сбоя {model_name}"
                )

        raise last_error if last_error else RuntimeError("Groq: неизвестная ошибка")

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
    def get_interview_system_prompt(
        cls, fmt: str, company: str, title: str, description: str
    ) -> str:
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
        dialog = "\n".join(
            f"[{'Интервьюер' if m['role'] == 'assistant' else 'Кандидат'}]: {m['content']}"
            for m in history
            if m["role"] in ("assistant", "user")
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
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"ЗАПИСЬ ИНТЕРВЬЮ:\n{dialog[:6000]}"},
            ],
            temperature=0.2,
            json_mode=True,
            max_tokens=900,
            model=self.analysis_model,
        )
        return json.loads(content)
