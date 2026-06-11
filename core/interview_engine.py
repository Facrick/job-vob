import json
import logging
import os
import time

from core.config import AppConfig
from core.groq_client import make_groq_client


class MockInterviewEngine:
    def __init__(self):
        self.config = AppConfig()
        self.api_key = os.getenv("GROQ_API_KEY")
        if not self.api_key:
            raise ValueError("GROQ_API_KEY не найден в .env")
        self.client = make_groq_client(self.api_key)
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

    # ── Уровни сложности ──────────────────────────────────────────────
    _LEVELS: dict[str, dict] = {
        "junior": {
            "label": "Junior",
            "note": ("Уровень кандидата — JUNIOR. Вопросы — базовые и средние: "
                     "основы, определения, простые практические кейсы. Тон поддерживающий."),
        },
        "middle": {
            "label": "Middle",
            "note": ("Уровень кандидата — MIDDLE. Вопросы средней сложности с "
                     "практическими сценариями, проверяй самостоятельность и опыт."),
        },
        "senior": {
            "label": "Senior",
            "note": ("Уровень кандидата — SENIOR. Вопросы сложные: архитектура, "
                     "trade-offs, нетривиальные кейсы, обоснование решений. Копай вглубь."),
        },
    }

    @classmethod
    def get_interview_system_prompt(
        cls, fmt: str, company: str, title: str, description: str,
        level: str = "middle", resume_text: str = "",
    ) -> str:
        tpl = cls._INTERVIEW_FORMATS.get(fmt, cls._INTERVIEW_FORMATS["tech"])["system"]
        prompt = tpl.format(company=company, title=title, description=description[:2000])

        level_note = cls._LEVELS.get(level, cls._LEVELS["middle"])["note"]
        prompt += f"\n\n{level_note}"

        if resume_text and resume_text.strip():
            prompt += (
                "\n\nРЕЗЮМЕ КАНДИДАТА (фрагмент):\n"
                f"{resume_text.strip()[:1800]}\n\n"
                "Задавай ЧАСТЬ вопросов по реальному опыту и стеку из резюме: "
                "проси раскрыть заявленные проекты/навыки, проверяй их подлинность и "
                "нащупывай пробелы относительно требований вакансии."
            )
        return prompt

    def generate_mock_reply(self, messages_history: list[dict[str, str]]) -> str:
        try:
            content = self._complete(
                messages_history, temperature=0.5, json_mode=False, max_tokens=800
            )
            return content.strip()
        except Exception as e:
            logging.error(f"Ошибка в mock-интервью: {e}")
            return "Извините, произошла техническая ошибка."

    # ── Разбор отдельного ответа (теория + эталон) ────────────────────
    def analyze_answer(
        self, question: str, answer: str, fmt: str, title: str, company: str,
        level: str = "middle",
    ) -> dict:
        """Обучающий разбор одного ответа кандидата.

        → JSON {score, verdict, correct[], mistakes[], theory, model_answer}.
        Теорию и эталон даёт ВСЕГДА (это тренажёр), даже если ответа по сути нет.
        Оценка калибруется под уровень (level): для junior планка ниже, для senior выше.
        """
        fmt_info = self._INTERVIEW_FORMATS.get(fmt, self._INTERVIEW_FORMATS["tech"])
        persona = fmt_info["label"].lower()
        level_label = self._LEVELS.get(level, self._LEVELS["middle"])["label"]
        system_prompt = (
            f"Оценивай по планке уровня {level_label}. "
            f"Ты — наставник-эксперт по подготовке к собеседованиям. Разбираешь ответ "
            f"кандидата на {persona} интервью на позицию «{title}». Цель — НАУЧИТЬ: "
            "честно укажи ошибки и дай правильную теорию.\n\n"
            "Верни СТРОГО JSON:\n"
            "{\n"
            '  "score": <целое 1-10>,\n'
            '  "verdict": "Зачтено | Частично | Неверно",\n'
            '  "correct": ["что в ответе верно/удачно", ...],\n'
            '  "mistakes": ["ошибка или что упущено — конкретно", ...],\n'
            '  "theory": "Правильная теория по теме вопроса: по делу, понятно, 3-6 предложений. Можно списком ключевых пунктов.",\n'
            '  "model_answer": "Краткий эталонный ответ — как ответил бы сильный кандидат (2-5 предложений)."\n'
            "}\n"
            "Если ответ пустой/«не знаю» — score низкий, correct может быть пустым, "
            "но theory и model_answer заполни обязательно."
        )
        user_prompt = (
            f"ВОПРОС ИНТЕРВЬЮЕРА:\n{question}\n\n"
            f"ОТВЕТ КАНДИДАТА:\n{answer or '(ответа нет)'}"
        )
        content = self._complete(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_prompt}],
            temperature=0.2, json_mode=True, max_tokens=900, model=self.analysis_model,
        )
        data = json.loads(content)
        # Нормализация типов для UI.
        data["score"] = int(data.get("score", 0) or 0)
        for k in ("correct", "mistakes"):
            v = data.get(k)
            data[k] = v if isinstance(v, list) else ([v] if v else [])
        data["theory"] = str(data.get("theory") or "")
        data["model_answer"] = str(data.get("model_answer") or "")
        data["verdict"] = str(data.get("verdict") or "")
        return data

    def get_hint(self, question: str, fmt: str, title: str) -> str:
        """Короткая подсказка по текущему вопросу — направление, без полного ответа."""
        system_prompt = (
            "Ты помогаешь кандидату на собеседовании. Дай КОРОТКУЮ подсказку "
            "(1–2 предложения): направление мысли и 2–3 ключевых термина. "
            "НЕ давай полный ответ — только наводку."
        )
        content = self._complete(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": f"Вопрос: {question}"}],
            temperature=0.3, json_mode=False, max_tokens=180, model=self.analysis_model,
        )
        return content.strip()

    def get_model_answer(self, question: str, fmt: str, title: str) -> dict:
        """Эталонный ответ + теория по текущему вопросу → {model_answer, theory}."""
        system_prompt = (
            f"Ты — эксперт по теме интервью на позицию «{title}». Дай образцовый ответ "
            "на вопрос и краткую теорию.\n\n"
            "Верни СТРОГО JSON:\n"
            '{ "model_answer": "Эталонный ответ (3-6 предложений).",'
            ' "theory": "Ключевая теория по теме: понятно и по делу." }'
        )
        content = self._complete(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": f"Вопрос: {question}"}],
            temperature=0.3, json_mode=True, max_tokens=700, model=self.analysis_model,
        )
        data = json.loads(content)
        return {
            "model_answer": str(data.get("model_answer") or ""),
            "theory": str(data.get("theory") or ""),
        }

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
