"""Вкладка 3 — Mock-собеседование."""
from nicegui import ui

from gui_ng.views._shared import _card, _scroll, _split, _section_head


def build_interview_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                with ui.element("div").classes("vob-sec-icon").style("--vob-accent:#60a5fa"):
                    ui.icon("work_outline")
                ui.label("Вакансия:").classes("text-sm font-semibold").style(
                    "white-space:nowrap"
                )
                el["interview_vacancy_select"] = ui.select(
                    options={}, label="Выберите вакансию…",
                    on_change=c.handle_interview_vacancy_select,
                ).props("dense outlined use-input input-debounce=300 clearable").classes(
                    "flex-grow"
                )
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                with ui.element("div").classes("vob-sec-icon").style("--vob-accent:#a78bfa"):
                    ui.icon("psychology")
                ui.label("Mock-собеседование с ИИ").classes("text-base font-semibold")
                el["combo_format"] = ui.select(
                    {"tech": "Техническое", "hr": "HR-скрининг",
                     "system_design": "System Design", "behavioral": "Поведенческое (STAR)"},
                    value="tech", label="Формат",
                ).props("dense outlined").classes("ml-4").style("min-width:170px")
                el["combo_level"] = ui.select(
                    {"junior": "Junior", "middle": "Middle", "senior": "Senior"},
                    value="middle", label="Уровень",
                ).props("dense outlined").style("min-width:120px")
                el["toggle_resume"] = ui.switch("По резюме", value=True).props(
                    "dense"
                ).tooltip("Задавать часть вопросов по вашему резюме и проверять заявленные навыки")
                ui.space()
                el["btn_start"] = ui.button(
                    "Начать", icon="play_arrow", on_click=c.handle_start_mock
                ).props("no-caps flat").classes("vob-btn-accent vob-eq-btn")
                el["btn_evaluate"] = ui.button(
                    "Оценить сессию", icon="assessment", on_click=c.handle_evaluate_interview
                ).props("outline no-caps").classes("vob-eq-btn")
                el["btn_evaluate"].set_visibility(False)
                el["btn_reset"] = ui.button(
                    "Сбросить", icon="refresh", on_click=c.handle_reset_mock
                ).props("outline no-caps").classes("vob-eq-btn")
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                el["interview_vacancy_label"] = ui.label("Вакансия не выбрана").classes(
                    "text-xs vob-muted italic flex-grow"
                )
                el["interview_progress"] = ui.linear_progress(
                    show_value=False,
                ).props("color=primary indeterminate").classes("w-32")
                el["interview_progress"].set_visibility(False)
                el["interview_status"] = ui.label("").classes("text-xs vob-muted")
                el["interview_status"].set_visibility(False)
        with _split(60) as sp:
            with sp.before:
                with _card("h-full"):
                    el["chat_arena"] = _scroll("gap-2")
                    with el["chat_arena"]:
                        with ui.column().classes(
                            "w-full h-full items-center justify-center gap-2"
                        ):
                            ui.icon("forum", size="40px").style("color:#3f3f46")
                            ui.label(
                                "Выберите вакансию, формат и уровень, "
                                "затем нажмите «Начать»."
                            ).classes("italic vob-muted text-sm text-center")
            with sp.after:
                with _card("h-full"):
                    _section_head("assessment", "Отчёт по сессии", "#fb7a3c")
                    el["report_box"] = _scroll("gap-2")
                    with el["report_box"]:
                        ui.label("Завершите сессию и нажмите «Оценить сессию»").classes(
                            "italic vob-muted text-sm"
                        )
        with _card().classes("vob-action-bar"):
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                el["input_chat"] = ui.input(placeholder="Ваш ответ…").props(
                    "dense outlined"
                ).classes("flex-grow").on("keydown.enter", c.handle_send_chat)
                el["btn_hint"] = ui.button(
                    "Подсказка", icon="lightbulb", on_click=c.handle_show_hint
                ).props("outline no-caps dense").classes("vob-act-btn").tooltip(
                    "Короткая наводка по текущему вопросу (без полного ответа)"
                )
                el["btn_model"] = ui.button(
                    "Эталон", icon="menu_book", on_click=c.handle_show_model_answer
                ).props("outline no-caps dense").classes("vob-act-btn").tooltip(
                    "Показать эталонный ответ и теорию по текущему вопросу"
                )
                el["btn_send"] = ui.button(
                    "Отправить", icon="send", on_click=c.handle_send_chat
                ).props("no-caps flat").classes("vob-btn-accent vob-act-btn")
