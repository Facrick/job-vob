"""Вкладка 3 — Mock-собеседование."""
from nicegui import ui

from gui_ng.views._shared import _card, _scroll, _split


def build_interview_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("psychology", color="primary")
                ui.label("Mock-собеседование с ИИ").classes("text-base font-semibold")
                el["combo_format"] = ui.select(
                    {"tech": "Техническое", "hr": "HR-скрининг",
                     "system_design": "System Design", "behavioral": "Поведенческое (STAR)"},
                    value="tech", label="Формат",
                ).props("dense outlined").classes("ml-4").style("min-width:180px")
                ui.space()
                el["btn_start"] = ui.button(
                    "Начать", icon="play_arrow", on_click=c.handle_start_mock
                ).props("no-caps")
                el["btn_evaluate"] = ui.button(
                    "Оценить сессию", icon="assessment", on_click=c.handle_evaluate_interview
                ).props("outline no-caps")
                el["btn_evaluate"].set_visibility(False)
                el["btn_reset"] = ui.button(
                    "Сбросить", icon="refresh", on_click=c.handle_reset_mock
                ).props("outline no-caps")
            el["interview_vacancy_label"] = ui.label("Вакансия не выбрана").classes(
                "text-xs vob-muted italic"
            )
        with _split(60) as sp:
            with sp.before:
                with _card("h-full"):
                    el["chat_arena"] = _scroll("gap-2")
            with sp.after:
                with _card("h-full"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("assessment", color="primary")
                        ui.label("Отчёт по сессии").classes("text-base font-semibold")
                    el["report_box"] = _scroll("gap-2")
                    with el["report_box"]:
                        ui.label("Завершите сессию и нажмите «Оценить сессию»").classes(
                            "italic vob-muted text-sm"
                        )
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                el["input_chat"] = ui.input("Ваш ответ...").props(
                    "dense outlined"
                ).classes("flex-grow").on("keydown.enter", c.handle_send_chat)
                el["btn_send"] = ui.button(
                    "Отправить", icon="send", on_click=c.handle_send_chat
                ).props("no-caps")
