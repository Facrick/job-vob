import logging

from core.ai._base import BaseAIClient


class MockInterviewEngine(BaseAIClient):
    def __init__(self):
        super().__init__(log_prefix="[AI-Interview]")

    # ── Форматы интервью ──────────────────────────────────────────────────
    # Все промпты используют {title}, {company}, {description} — без QA-хардкодов.
    _INTERVIEW_FORMATS: dict[str, dict] = {
        "tech": {
            "label": "Техническое",
            "system": (
                "Ты — опытный технический интервьюер в компании {company}. "
                "Проводишь техническое интервью на позицию «{title}».\n"
                "Требования из вакансии:\n{description}\n\n"
                "Задавай вопросы строго по специфике этой роли и стека. "
                "Представься и задай ОДИН конкретный технический вопрос. "
                "Не пиши за кандидата."
            ),
            "eval_system": (
                "Ты — объективный эксперт по техническим интервью. "
                "Оцени кандидата на позицию «{title}» в компании {company} "
                "по пяти ключевым компетенциям для ЭТОЙ конкретной роли:\n"
                "1. Профессиональные технические знания по роли\n"
                "2. Практический опыт и примеры из работы\n"
                "3. Знание инструментов и технологий из вакансии\n"
                "4. Качество решений и аргументация\n"
                "5. Глубина понимания предметной области"
            ),
        },
        "hr": {
            "label": "HR-скрининг",
            "system": (
                "Ты — профессиональный HR-менеджер в компании {company}. "
                "Проводишь HR-скрининг кандидата на позицию «{title}». "
                "Фокус: мотивация, soft skills, карьерные цели, culture fit, командная работа. "
                "Задавай поведенческие вопросы. Никаких технических вопросов. "
                "Представься, объясни формат и задай первый вопрос."
            ),
            "eval_system": (
                "Ты — объективный HR-эксперт. "
                "Оцени кандидата на позицию «{title}» в компании {company} "
                "по пяти HR-компетенциям:\n"
                "1. Коммуникация и самопрезентация\n"
                "2. Мотивация и интерес к роли\n"
                "3. Cultural Fit и командная работа\n"
                "4. Карьерные цели и адекватность ожиданий\n"
                "5. Эмоциональный интеллект и стрессоустойчивость"
            ),
        },
        "system_design": {
            "label": "System Design",
            "system": (
                "Ты — опытный архитектор в компании {company}. "
                "Проводишь System Design интервью на позицию «{title}».\n"
                "Описание роли:\n{description}\n\n"
                "Предложи кандидату спроектировать систему или архитектурное решение, "
                "релевантное этой роли и компании. "
                "Оценивай: структурность подхода, полноту решения, выбор технологий, "
                "понимание trade-offs и рисков. "
                "Представься, опиши задачу и жди ответа. Задавай уточняющие вопросы."
            ),
            "eval_system": (
                "Ты — объективный эксперт по System Design. "
                "Оцени кандидата на позицию «{title}» в компании {company} "
                "по пяти компетенциям System Design:\n"
                "1. Системное мышление и декомпозиция задачи\n"
                "2. Полнота и обоснованность решения\n"
                "3. Знание технологий и инструментов\n"
                "4. Управление компромиссами (trade-offs)\n"
                "5. Структурность изложения"
            ),
        },
        "behavioral": {
            "label": "Поведенческое (STAR)",
            "system": (
                "Ты — опытный интервьюер в компании {company}. "
                "Проводишь поведенческое интервью на позицию «{title}» по методике STAR. "
                "После каждого ответа давай краткую оценку структуры (Situation/Task/Action/Result) "
                "и задавай следующий вопрос. "
                "Темы вопросов: сложные ситуации в работе, конфликты в команде, "
                "жёсткие дедлайны, неудачный проект, быстрое обучение новому. "
                "Представься и начни с первого STAR-вопроса."
            ),
            "eval_system": (
                "Ты — объективный эксперт по поведенческим интервью. "
                "Оцени кандидата на позицию «{title}» в компании {company} "
                "по пяти поведенческим компетенциям (методика STAR):\n"
                "1. Структура ответов (Situation/Task/Action/Result)\n"
                "2. Командная работа и коллаборация\n"
                "3. Управление конфликтами и сложными ситуациями\n"
                "4. Обучаемость и адаптивность\n"
                "5. Ответственность за результат"
            ),
        },
    }

    # ── Уровни сложности ──────────────────────────────────────────────────
    _LEVELS: dict[str, dict] = {
        "junior": {
            "label": "Junior",
            "note": (
                "Уровень кандидата — JUNIOR. Задавай базовые и средние вопросы: "
                "основы роли, определения, простые практические кейсы. "
                "Тон поддерживающий, не давящий."
            ),
        },
        "middle": {
            "label": "Middle",
            "note": (
                "Уровень кандидата — MIDDLE. Вопросы средней сложности "
                "с практическими сценариями. Проверяй самостоятельность и реальный опыт."
            ),
        },
        "senior": {
            "label": "Senior",
            "note": (
                "Уровень кандидата — SENIOR. Вопросы сложные: архитектура, "
                "trade-offs, нетривиальные кейсы, обоснование решений. Копай вглубь."
            ),
        },
    }

    @classmethod
    def get_interview_system_prompt(
        cls, fmt: str, company: str, title: str, description: str,
        level: str = "middle", resume_text: str = "",
    ) -> str:
        tpl = cls._INTERVIEW_FORMATS.get(fmt, cls._INTERVIEW_FORMATS["tech"])["system"]
        prompt = tpl.format(
            company=company or "компании",
            title=title or "данной позиции",
            description=(description or "")[:2000],
        )

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

    # ── Разбор отдельного ответа ──────────────────────────────────────────
    def analyze_answer(
        self, question: str, answer: str, fmt: str, title: str, company: str,
        level: str = "middle",
    ) -> dict:
        """Обучающий разбор одного ответа кандидата.

        → JSON {score, verdict, correct[], mistakes[], theory, model_answer}.
        Оценка калибруется под уровень (level) и специфику роли (title).
        """
        level_label = self._LEVELS.get(level, self._LEVELS["middle"])["label"]
        fmt_label = self._INTERVIEW_FORMATS.get(fmt, self._INTERVIEW_FORMATS["tech"])["label"].lower()
        system_prompt = (
            f"Ты — наставник-эксперт, готовишь кандидата к собеседованию "
            f"на позицию «{title or 'данную роль'}». "
            f"Формат интервью: {fmt_label}. Уровень кандидата: {level_label}.\n\n"
            "Разбери ответ честно и по делу — цель НАУЧИТЬ.\n\n"
            "Верни СТРОГО JSON:\n"
            "{\n"
            '  "score": <целое 1-10>,\n'
            '  "verdict": "Зачтено | Частично | Неверно",\n'
            '  "correct": ["что верно или удачно в ответе", ...],\n'
            '  "mistakes": ["конкретная ошибка или упущение", ...],\n'
            '  "theory": "Правильная теория по теме вопроса: по делу, '
            'понятно, 3-6 предложений.",\n'
            '  "model_answer": "Как ответил бы сильный кандидат уровня '
            f'{level_label} на эту позицию (2-5 предложений)."\n'
            "}\n"
            "Если ответ пустой/«не знаю» — score низкий, correct пустой, "
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
        data = self._parse_json_safe(content)
        data["score"] = int(data.get("score", 0) or 0)
        for k in ("correct", "mistakes"):
            v = data.get(k)
            data[k] = v if isinstance(v, list) else ([v] if v else [])
        data["theory"] = str(data.get("theory") or "")
        data["model_answer"] = str(data.get("model_answer") or "")
        data["verdict"] = str(data.get("verdict") or "")
        return data

    def get_hint(self, question: str, fmt: str, title: str) -> str:
        """Короткая подсказка по текущему вопросу — направление без полного ответа."""
        system_prompt = (
            f"Ты помогаешь кандидату на интервью на позицию «{title or 'данную роль'}». "
            "Дай КОРОТКУЮ подсказку (1-2 предложения): направление мысли и "
            "2-3 ключевых термина. НЕ давай полный ответ — только наводку."
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
            f"Ты — эксперт по роли «{title or 'данная позиция'}». "
            "Дай образцовый ответ на вопрос и краткую теорию по теме.\n\n"
            "Верни СТРОГО JSON:\n"
            '{"model_answer": "Эталонный ответ (3-6 предложений).", '
            '"theory": "Ключевая теория по теме: понятно и по делу."}'
        )
        content = self._complete(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": f"Вопрос: {question}"}],
            temperature=0.3, json_mode=True, max_tokens=700, model=self.analysis_model,
        )
        data = self._parse_json_safe(content)
        return {
            "model_answer": str(data.get("model_answer") or ""),
            "theory": str(data.get("theory") or ""),
        }

    def evaluate_mock_interview(
        self, history: list[dict], fmt: str, title: str, company: str
    ) -> dict:
        """Оценивает сессию mock-интервью → JSON с компетенциями и рекомендацией."""
        fmt_info = self._INTERVIEW_FORMATS.get(fmt, self._INTERVIEW_FORMATS["tech"])
        eval_system = fmt_info["eval_system"].format(
            title=title or "данной позиции",
            company=company or "компании",
        )
        dialog = "\n".join(
            f"[{'Интервьюер' if m['role'] == 'assistant' else 'Кандидат'}]: {m['content']}"
            for m in history
            if m["role"] in ("assistant", "user")
        )
        system_prompt = (
            f"{eval_system}\n\n"
            "Верни СТРОГО JSON-объект:\n"
            "{\n"
            '  "summary": "2-3 предложения: общее впечатление о кандидате",\n'
            '  "competencies": [\n'
            '    {"name": "Название компетенции", "score": 8, '
            '"comment": "1 предложение"}, ...\n'
            "  ],\n"
            '  "strengths": ["сильная сторона 1", "сильная сторона 2"],\n'
            '  "improvements": ["что улучшить 1", "что улучшить 2"],\n'
            '  "recommendation": "Рекомендую к следующему этапу / '
            'Нужна дополнительная подготовка / Не рекомендую"\n'
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
        return self._parse_json_safe(content)
