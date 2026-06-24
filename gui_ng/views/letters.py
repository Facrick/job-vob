"""Вкладка 2 — Письма / автоотклик."""
from nicegui import ui

from gui_ng.views._shared import _card, _split, _section_head


def build_letters_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        # ── Панель выбора вакансии ────────────────────────────────────────────
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                with ui.element("div").classes("vob-sec-icon").style("--vob-accent:#60a5fa"):
                    ui.icon("work_outline")
                ui.label("Вакансия:").classes("text-sm font-semibold").style(
                    "white-space:nowrap"
                )
                el["letter_vacancy_select"] = ui.select(
                    options={}, label="Выберите вакансию…",
                    on_change=c.handle_letter_vacancy_select,
                ).props("dense outlined use-input input-debounce=300 clearable").classes(
                    "flex-grow"
                )
                # скрытый лейбл — нужен контроллеру для синхронизации с CRM
                el["letter_vacancy_label"] = ui.label("").classes(
                    "text-xs vob-muted"
                ).style("display:none")
                el["letter_progress"] = ui.linear_progress(
                    show_value=False,
                ).props("color=primary indeterminate").classes("w-32")
                el["letter_progress"].set_visibility(False)
                el["letter_status"] = ui.label("").classes("text-xs vob-muted")
                el["letter_status"].set_visibility(False)

        # ── Основная область: письмо + рекомендации ───────────────────────────
        with _split(60) as sp:
            with sp.before:
                with _card("h-full"):
                    _section_head("description", "Текст письма", "#a78bfa")
                    el["text_letter"] = ui.textarea(
                    ).props("outlined").classes("w-full flex-grow vob-fill").on(
                        "blur", c.handle_letter_text_blur
                    )
            with sp.after:
                with _card("h-full"):
                    _section_head("lightbulb", "Рекомендации ИИ", "#fb7a3c")
                    el["text_recs"] = ui.textarea(
                    ).props("outlined readonly").classes("w-full flex-grow vob-fill")

        # ── Панель действий (тулбар) ──────────────────────────────────────────
        with _card().classes("vob-action-bar"):
            # Ряд 1: создание/правка письма — генерация + поле фидбека + исправить
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                el["btn_generate_letters"] = ui.button(
                    "Сгенерировать", icon="auto_awesome",
                    on_click=lambda: c.handle_generation("btn_generate_letters"),
                ).props("no-caps flat").classes("vob-btn-accent vob-act-btn").tooltip(
                    "ИИ сгенерирует письмо по выбранной вакансии и резюме"
                )
                el["input_feedback"] = ui.input(
                    placeholder="Что исправить в письме?"
                ).props("dense outlined").classes("flex-grow").on(
                    "keydown.enter", c.handle_feedback
                )
                el["btn_feedback"] = ui.button(
                    "Исправить", icon="edit", on_click=c.handle_feedback
                ).props("outline no-caps dense").classes("vob-act-btn")

            # Ряд 2: вспомогательные действия слева + финальная отправка справа
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                el["btn_copy"] = ui.button(
                    "Копировать", icon="content_copy", on_click=c.copy_letter
                ).props("outline no-caps dense").classes("vob-act-btn").tooltip(
                    "Скопировать письмо в буфер"
                )
                el["btn_letter_history"] = ui.button(
                    "История", icon="history", on_click=c.handle_letter_history
                ).props("outline no-caps dense").classes("vob-act-btn").tooltip(
                    "Просмотреть прошлые версии письма"
                )
                el["btn_score_letter"] = ui.button(
                    "Оценить", icon="grade", on_click=c.handle_score_letter
                ).props("outline no-caps dense").classes("vob-act-btn").tooltip(
                    "ИИ оценит письмо по 4 критериям"
                )
                ui.space()
                el["btn_auto_apply"] = ui.button(
                    "Отправить автоотклик", icon="send", on_click=c.handle_auto_apply,
                ).props("no-caps flat").classes("vob-btn-accent vob-act-btn")
