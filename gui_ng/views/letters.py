"""Вкладка 2 — Письма / автоотклик."""
from nicegui import ui

from gui_ng.views._shared import _card, _split


def build_letters_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        with _split(60) as sp:
            with sp.before:
                with _card("h-full"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("description", color="primary")
                        ui.label("Текст письма").classes("text-base font-semibold")
                        ui.space()
                        el["letter_vacancy_label"] = ui.label(
                            "Вакансия не выбрана — выберите её в CRM"
                        ).classes("text-sm vob-muted italic")
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
            el["btn_auto_apply"] = ui.button(
                "Отправить автоотклик", icon="send", on_click=c.handle_auto_apply,
                color="positive",
            ).props("no-caps").classes("w-full")
