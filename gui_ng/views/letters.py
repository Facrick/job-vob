"""Вкладка 2 — Письма / автоотклик."""
from nicegui import ui

from gui_ng.views._shared import _card, _split


def build_letters_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        # ── Панель выбора вакансии ────────────────────────────────────────────
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("work_outline", color="primary")
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
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("description", color="primary")
                        ui.label("Текст письма").classes("text-base font-semibold")
                    el["text_letter"] = ui.textarea(
                        placeholder="Сопроводительное письмо появится здесь после генерации…"
                    ).props("outlined").classes("w-full flex-grow vob-fill")
            with sp.after:
                with _card("h-full"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("lightbulb", color="primary")
                        ui.label("Рекомендации ИИ").classes("text-base font-semibold")
                    el["text_recs"] = ui.textarea(
                        placeholder="Рекомендации ИИ появятся здесь после генерации…"
                    ).props("outlined readonly").classes("w-full flex-grow vob-fill")

        # ── Панель действий ───────────────────────────────────────────────────
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                el["input_feedback"] = ui.input(
                    placeholder="Что исправить?"
                ).props("dense outlined").classes("flex-grow").on(
                    "keydown.enter", c.handle_feedback
                )
                el["btn_feedback"] = ui.button(
                    "Исправить", icon="edit", on_click=c.handle_feedback
                ).props("outline no-caps")
                el["btn_copy"] = ui.button(
                    "Копировать", icon="content_copy", on_click=c.copy_letter
                ).props("outline no-caps").tooltip("Скопировать письмо в буфер")
                el["btn_letter_history"] = ui.button(
                    "История", icon="history", on_click=c.handle_letter_history
                ).props("outline no-caps").tooltip("Просмотреть прошлые версии письма")
                el["btn_score_letter"] = ui.button(
                    "Оценить", icon="grade", on_click=c.handle_score_letter
                ).props("outline no-caps").tooltip("ИИ оценит письмо по 4 критериям")
            el["btn_auto_apply"] = ui.button(
                "Отправить автоотклик", icon="send", on_click=c.handle_auto_apply,
                color="positive",
            ).props("no-caps").classes("w-full")
