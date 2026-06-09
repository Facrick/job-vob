"""Вкладка «Интервью»: mock-собеседование и отчёт."""
import logging

from nicegui import run, ui

from gui_ng.controllers._helpers import _q


class _InterviewMixin:
    """Методы mock-собеседования: запуск сессии, чат, оценка, отчёт."""

    async def handle_start_mock(self):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        fmt = self.el["combo_format"].value or "tech"
        system_msg = self.interview_engine.get_interview_system_prompt(
            fmt, v["company"], v["title"], v.get("description", "")
        )
        self.mock_chat_history = [{"role": "system", "content": system_msg}]
        self._clear_report()
        self.el["btn_start"].disable()
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

    async def handle_send_chat(self):
        user_text = (self.el["input_chat"].value or "").strip()
        if not user_text or not self.mock_chat_history:
            return
        self.mock_chat_history.append({"role": "user", "content": user_text})
        self.el["input_chat"].set_value("")
        self._render_mock_chat()
        self.el["btn_send"].disable()
        try:
            messages = list(self.mock_chat_history) + [{
                "role": "system",
                "content": "Оцени ответ по 10-балльной шкале, укажи ошибки. Задай следующий вопрос.",
            }]
            reply = await run.io_bound(self.interview_engine.generate_mock_reply, messages)
            self.mock_chat_history.append({"role": "assistant", "content": reply})
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
            self._render_mock_chat()
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_send"].enable()

    async def handle_evaluate_interview(self):
        if len([m for m in self.mock_chat_history if m["role"] == "user"]) < 2:
            self._show_error("Проведите хотя бы 2–3 обмена репликами перед оценкой.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id) if self.selected_vacancy_id else {}
        fmt = self.el["combo_format"].value or "tech"
        self.el["btn_evaluate"].disable()
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

    def handle_reset_mock(self):
        self.mock_chat_history = []
        if self.selected_vacancy_id:
            self.repo.save_mock_interview(self.selected_vacancy_id, [])
        self.el["chat_arena"].clear()
        self.el["btn_evaluate"].set_visibility(False)
        self._clear_report()

    def _render_mock_chat(self):
        arena = self.el.get("chat_arena")
        if arena is None:
            return
        arena.clear()
        with arena:
            for msg in self.mock_chat_history:
                if msg["role"] == "assistant":
                    ui.chat_message(msg["content"], name="Тимлид", sent=False)
                elif msg["role"] == "user":
                    ui.chat_message(msg["content"], name="Вы", sent=True)

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
