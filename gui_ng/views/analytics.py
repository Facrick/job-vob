"""Вкладка 4 — Аналитика / воронка / зарплаты / хитмап."""
from nicegui import ui

from gui_ng.views._shared import _card, _scroll, _split


def build_analytics_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        with _card():
            with ui.row().classes("items-center gap-2"):
                ui.icon("filter_alt", color="primary")
                ui.label("Воронка поиска работы").classes("text-base font-semibold")
            el["funnel_box"] = ui.column().classes("w-full gap-3")
        with _card():
            with ui.row().classes("w-full items-center gap-2"):
                ui.icon("timeline", color="primary")
                ui.label("Timeline активности").classes("text-base font-semibold")
                ui.space()
                el["combo_timeline_period"] = ui.select(
                    {"14": "14 дней", "30": "30 дней", "60": "60 дней", "90": "90 дней"},
                    value="30", label="Период",
                ).props("dense outlined").style("width:110px")
                ui.button(
                    "Построить", icon="timeline", on_click=c.draw_timeline
                ).props("no-caps")
            el["timeline_box"] = ui.column().classes("w-full gap-1")
            with el["timeline_box"]:
                ui.label(
                    "Нажмите «Построить», чтобы увидеть активность по дням."
                ).classes("italic vob-muted text-sm")
        with _split(50) as sp:
            with sp.before:
                with _card("h-full"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("query_stats", color="primary")
                        ui.label("Зарплаты на рынке").classes("text-base font-semibold")
                        ui.space()
                        ui.button(
                            "Построить", icon="bar_chart", on_click=c.draw_analytics_chart
                        ).props("no-caps")
                    el["salary_box"] = _scroll("gap-2")
                    with el["salary_box"]:
                        ui.label(
                            "Нажмите «Построить», чтобы увидеть статистику зарплат."
                        ).classes("italic vob-muted")
            with sp.after:
                with _card("h-full"):
                    with ui.row().classes("w-full items-center gap-2"):
                        ui.icon("leaderboard", color="primary")
                        ui.label("Топ навыков рынка").classes("text-base font-semibold")
                        ui.space()
                        el["combo_heatmap_n"] = ui.select(
                            {"10": "10", "20": "20", "30": "30"}, value="20", label="Топ",
                        ).props("dense outlined").style("width:90px")
                        ui.button(
                            "Хитмап", icon="leaderboard", on_click=c.draw_skill_heatmap
                        ).props("no-caps")
                    el["heatmap_box"] = _scroll("gap-2")
                    with el["heatmap_box"]:
                        ui.label(
                            "Нажмите «Хитмап», чтобы увидеть топ навыков."
                        ).classes("italic vob-muted")
