"""Вкладка 6 — Журнал событий."""
from nicegui import ui

from gui_ng.views._shared import _card


def build_logs_tab(c):
    el = c.el
    with _card("w-full h-full"):
        with ui.row().classes("w-full items-center gap-2"):
            ui.icon("terminal", color="primary")
            ui.label("Журнал событий").classes("text-base font-semibold")
            ui.space()
            ui.button("Очистить", icon="delete_sweep", on_click=c.handle_clear_logs).props(
                "outline no-caps"
            )
            ui.button("Копировать всё", icon="content_copy", on_click=c.handle_copy_logs).props(
                "outline no-caps"
            )
        el["logs"] = ui.log().classes("w-full flex-grow").style(
            "font-family:Consolas,monospace;font-size:12px;"
            "user-select:text;cursor:text"
        )
