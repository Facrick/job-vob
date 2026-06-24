"""Вкладка «Интервью»: mock-собеседование и отчёт."""
import logging

from nicegui import run, ui

from gui_ng.controllers._helpers import _q


class _InterviewMixin:
    """Методы mock-собеседования: запуск сессии, чат, оценка, отчёт."""

    def refresh_interview_vacancy_select(self) -> None:
        """Обновляет список вакансий в селекте вкладки Интервью."""
        sel = self.el.get("interview_vacancy_select")
        if not sel:
            return
        vacancies = self.repo.get_vacancies_filtered("all")
        options = {
            v["id"]: f"{v.get('company', '—')} — {v.get('title', '—')}"
            for v in vacancies if v.get("id")
        }
        sel.options = options
        sel.update()
        if self.selected_vacancy_id and self.selected_vacancy_id in options:
            sel.set_value(self.selected_vacancy_id)

    def handle_interview_vacancy_select(self, e) -> None:
        """Обрабатывает выбор вакансии прямо из вкладки Интервью."""
        vid = e.value
        if not vid:
            return
        self.select_vacancy(vid)

    async def handle_start_mock(self):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        fmt = self.el["combo_format"].value or "tech"
        level = self.el["combo_level"].value or "middle"
        resume_text = self._safe_resume_text() if self.el["toggle_resume"].value else ""
        system_msg = self.interview_engine.get_interview_system_prompt(
            fmt, v["company"], v["title"], v.get("description", ""),
            level=level, resume_text=resume_text,
        )
        self.mock_chat_history = [{"role": "system", "content": system_msg}]
        self.mock_reviews = {}   # index ответа кандидата → разбор {score, theory, …}
        self._clear_report()
        self.el["btn_start"].disable()
        self._show_progress("ИИ-интервьюер готовит первый вопрос…",
                            key_progress="interview_progress", key_status="interview_status")
        try:
            reply = await run.io_bound(
                self.interview_engine.generate_mock_reply, self.mock_chat_history
            )
            self.mock_chat_history.append({"role": "assistant", "content": reply})
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
            self.el["btn_evaluate"].set_visibility(True)
            self._render_mock_chat()
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_start"].enable()
            self._hide_progress(key_progress="interview_progress",
                                key_status="interview_status")

    def _current_question(self) -> str:
        """Последний вопрос интервьюера (последняя реплика assistant)."""
        for m in reversed(self.mock_chat_history or []):
            if m["role"] == "assistant":
                return m["content"]
        return ""

    async def handle_send_chat(self):
        user_text = (self.el["input_chat"].value or "").strip()
        if not user_text or not self.mock_chat_history:
            return
        question = self._current_question()
        # Индекс этого ответа = сколько ответов кандидата уже было.
        answer_idx = sum(1 for m in self.mock_chat_history if m["role"] == "user")
        self.mock_chat_history.append({"role": "user", "content": user_text})
        self.el["input_chat"].set_value("")
        self._render_mock_chat()
        self.el["btn_send"].disable()
        self._show_progress("ИИ анализирует ответ и готовит следующий вопрос…",
                            key_progress="interview_progress", key_status="interview_status")

        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id) if self.selected_vacancy_id else {}
        fmt = self.el["combo_format"].value or "tech"
        title, company = (v or {}).get("title", ""), (v or {}).get("company", "")
        try:
            # 1) Обучающий разбор ответа (теория + эталон) — показываем отдельно.
            try:
                level = self.el["combo_level"].value or "middle"
                review = await run.io_bound(
                    self.interview_engine.analyze_answer,
                    question, user_text, fmt, title, company, level,
                )
                if not hasattr(self, "mock_reviews"):
                    self.mock_reviews = {}
                self.mock_reviews[answer_idx] = review
            except Exception as ex:
                logging.warning(f"[Interview] разбор ответа не удался: {ex}")

            # 2) Интервьюер задаёт СЛЕДУЮЩИЙ вопрос (без развёрнутой оценки —
            #    она уже в разборе). Короткая реакция + новый вопрос.
            messages = list(self.mock_chat_history) + [{
                "role": "system",
                "content": ("Кратко (1 фраза) отреагируй и задай СЛЕДУЮЩИЙ вопрос. "
                            "Не давай развёрнутую оценку — разбор выводится отдельно."),
            }]
            reply = await run.io_bound(self.interview_engine.generate_mock_reply, messages)
            self.mock_chat_history.append({"role": "assistant", "content": reply})
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
            self._render_mock_chat()
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_send"].enable()
            self._hide_progress(key_progress="interview_progress",
                                key_status="interview_status")

    async def handle_show_hint(self):
        question = self._current_question()
        if not question:
            self._show_error("Сначала начните интервью — нужен вопрос.")
            return
        fmt = self.el["combo_format"].value or "tech"
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id) if self.selected_vacancy_id else {}
        self.el["btn_hint"].disable()
        self._show_progress("ИИ генерирует подсказку…",
                            key_progress="interview_progress", key_status="interview_status")
        try:
            hint = await run.io_bound(
                self.interview_engine.get_hint, question, fmt, (v or {}).get("title", "")
            )
            self._show_coach_dialog("💡 Подсказка", hint_text=hint)
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_hint"].enable()
            self._hide_progress(key_progress="interview_progress",
                                key_status="interview_status")

    async def handle_show_model_answer(self):
        question = self._current_question()
        if not question:
            self._show_error("Сначала начните интервью — нужен вопрос.")
            return
        fmt = self.el["combo_format"].value or "tech"
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id) if self.selected_vacancy_id else {}
        self.el["btn_model"].disable()
        self._show_progress("ИИ формирует эталонный ответ…",
                            key_progress="interview_progress", key_status="interview_status")
        try:
            data = await run.io_bound(
                self.interview_engine.get_model_answer, question, fmt, (v or {}).get("title", "")
            )
            self._show_coach_dialog(
                "📝 Эталонный ответ",
                model_answer=data.get("model_answer", ""),
                theory=data.get("theory", ""),
            )
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_model"].enable()
            self._hide_progress(key_progress="interview_progress",
                                key_status="interview_status")

    def _show_coach_dialog(self, title: str, *, hint_text: str = "",
                           model_answer: str = "", theory: str = ""):
        with ui.dialog() as dlg, ui.card().style(
            "min-width:480px;max-width:680px;background:#141419;border:1px solid #26262f"
        ):
            ui.label(title).classes("text-base font-semibold").style("color:#fafafa")
            if hint_text:
                ui.markdown(hint_text).classes("text-sm")
            if model_answer:
                ui.label("Эталонный ответ").classes("text-xs font-semibold").style("color:#a78bfa")
                ui.markdown(model_answer).classes("text-sm")
            if theory:
                ui.label("Теория").classes("text-xs font-semibold").style("color:#a78bfa")
                ui.markdown(theory).classes("text-sm")
            with ui.row().classes("justify-end w-full"):
                ui.button("Закрыть", on_click=dlg.close).props("flat no-caps")
        dlg.open()

    async def handle_evaluate_interview(self):
        if len([m for m in self.mock_chat_history if m["role"] == "user"]) < 2:
            self._show_error("Проведите хотя бы 2–3 обмена репликами перед оценкой.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id) if self.selected_vacancy_id else {}
        fmt = self.el["combo_format"].value or "tech"
        self.el["btn_evaluate"].disable()
        self._show_progress("ИИ оценивает сессию интервью…",
                            key_progress="interview_progress", key_status="interview_status")
        try:
            data = await run.io_bound(
                self.interview_engine.evaluate_mock_interview,
                self.mock_chat_history, fmt, v.get("title", ""), v.get("company", ""),
            )
            self._render_report(data)
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_evaluate"].enable()
            self._hide_progress(key_progress="interview_progress",
                                key_status="interview_status")

    def handle_reset_mock(self):
        self.mock_chat_history = []
        self.mock_reviews = {}
        if self.selected_vacancy_id:
            self.repo.save_mock_interview(self.selected_vacancy_id, [])
        self._render_chat_placeholder()
        self.el["btn_evaluate"].set_visibility(False)
        self._clear_report()

    def _render_chat_placeholder(self):
        """Пустое состояние арены чата — до старта сессии."""
        arena = self.el.get("chat_arena")
        if arena is None:
            return
        arena.clear()
        with arena:
            with ui.column().classes(
                "w-full h-full items-center justify-center gap-2"
            ):
                ui.icon("forum", size="40px").style("color:#3f3f46")
                ui.label(
                    "Выберите вакансию, формат и уровень, затем нажмите «Начать»."
                ).classes("italic vob-muted text-sm text-center")

    def _render_mock_chat(self):
        arena = self.el.get("chat_arena")
        if arena is None:
            return
        if not self.mock_chat_history:
            self._render_chat_placeholder()
            return
        reviews = getattr(self, "mock_reviews", {}) or {}
        arena.clear()
        with arena:
            answer_idx = 0
            for msg in self.mock_chat_history:
                if msg["role"] == "assistant":
                    ui.chat_message(msg["content"], name="Тимлид", sent=False)
                elif msg["role"] == "user":
                    ui.chat_message(msg["content"], name="Вы", sent=True)
                    review = reviews.get(answer_idx)
                    if review:
                        self._render_review(review)
                    answer_idx += 1

    def _render_review(self, review: dict):
        """Карточка обучающего разбора ответа: оценка, ошибки, теория, эталон."""
        score = int(review.get("score", 0) or 0)
        color = "#66bb6a" if score >= 7 else "#ff8f00" if score >= 4 else "#ef5350"
        verdict = review.get("verdict", "") or ""
        header = f"Разбор ответа · {verdict} · {score}/10"
        with ui.expansion(header, icon="school").classes("w-full").props(
            "dense"
        ).style(
            f"background:rgba(167,139,250,.06);border:1px solid {color}55;"
            "border-radius:10px;margin:2px 0"
        ):
            correct = review.get("correct") or []
            if correct:
                ui.label("✅ Верно").classes("text-xs font-semibold").style("color:#66bb6a")
                ui.markdown("\n".join(f"- {c}" for c in correct)).classes("text-sm")
            mistakes = review.get("mistakes") or []
            if mistakes:
                ui.label("⚠️ Ошибки / упущено").classes("text-xs font-semibold").style("color:#ff8f00")
                ui.markdown("\n".join(f"- {m}" for m in mistakes)).classes("text-sm")
            theory = review.get("theory") or ""
            if theory:
                ui.label("📖 Теория").classes("text-xs font-semibold").style("color:#a78bfa")
                ui.markdown(theory).classes("text-sm")
            model_answer = review.get("model_answer") or ""
            if model_answer:
                ui.label("📝 Эталонный ответ").classes("text-xs font-semibold").style("color:#a78bfa")
                ui.markdown(model_answer).classes("text-sm")

    def _clear_report(self):
        self.el["report_box"].clear()
        with self.el["report_box"]:
            ui.label("Завершите сессию и нажмите «Оценить сессию»").classes(
                "italic vob-muted text-sm"
            )

    def _render_report(self, data: dict):
        box = self.el["report_box"]
        box.clear()
        with box:
            if data.get("summary"):
                ui.label(data["summary"]).classes("text-sm vob-muted")
            for comp in data.get("competencies", []):
                score = int(comp.get("score", 0))
                color = "#66bb6a" if score >= 7 else "#ff8f00" if score >= 4 else "#ef5350"
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(str(score)).style(
                            f"background-color:{color}33;color:#fff;font-weight:700"
                        )
                        ui.label(comp.get("name", "")).classes("font-medium")
                    ui.linear_progress(value=score / 10, show_value=False).props(
                        f"color={_q(color)}"
                    )
                    ui.label(comp.get("comment", "")).classes("text-xs vob-muted")
            strengths = data.get("strengths", [])
            if strengths:
                ui.label("✅ " + "\n✅ ".join(strengths)).classes("text-sm whitespace-pre-line")
            improvements = data.get("improvements", [])
            if improvements:
                ui.label("📌 " + "\n📌 ".join(improvements)).classes("text-sm whitespace-pre-line")
            rec = data.get("recommendation", "")
            if rec:
                color = ("#66bb6a" if "рекомендую" in rec.lower()
                         else "#ff8f00" if "подготовка" in rec.lower() else "#ef5350")
                ui.label(rec).style(
                    f"background-color:{color}20;color:#fff;font-weight:500;"
                    f"border:1px solid {color}55;padding:8px 12px;border-radius:8px"
                )
