"""Вкладка 4 — Аналитика / воронка / зарплаты / хитмап."""
from nicegui import ui

from core.synonyms import role_options
from gui_ng.views._shared import _card, _scroll, _split, _section_head


def build_analytics_tab(c):
    el = c.el
    # vob-scroll → вкладка прокручивается вертикально: воронка + timeline растут
    # по данным, поэтому без скролла нижние блоки (зарплаты/навыки) уезжали за
    # пределы экрана. min-height:0 нужен, чтобы скролл работал внутри flex-родителя.
    with ui.column().classes("w-full h-full no-wrap gap-3 vob-scroll").style(
        "min-height:0"
    ):
        # flex-shrink:0 — иначе во flex-колонке фиксированной высоты карточки
        # сжимаются, а overflow-hidden обрезает их контент до одной строки.
        with _card().style("flex:0 0 auto"):
            _section_head("filter_alt", "Воронка поиска работы", "#fb7a3c")
            el["funnel_box"] = ui.column().classes("w-full gap-3")
        with _card().style("flex:0 0 auto"):
            with _section_head("timeline", "Timeline активности", "#60a5fa"):
                ui.space()
                el["combo_timeline_period"] = ui.select(
                    {"14": "14 дней", "30": "30 дней", "60": "60 дней", "90": "90 дней"},
                    value="30", label="Период",
                ).props("dense outlined").style("width:110px")
                ui.button(
                    "Обновить", icon="refresh", on_click=c.draw_timeline
                ).props("no-caps flat dense").classes("vob-btn-refresh")
            el["timeline_box"] = ui.column().classes("w-full gap-1")
            with el["timeline_box"]:
                ui.label(
                    "Нажмите «Построить», чтобы увидеть активность по дням."
                ).classes("italic vob-muted text-sm")
        # Фиксированная высота вместо flex-растягивания: внутри прокручиваемой
        # колонки flex:1 схлопнул бы сплиттер, и графики были бы нечитаемо мелкими.
        with _split(50, height="460px") as sp:
            with sp.before:
                with _card("h-full"):
                    with _section_head("query_stats", "Зарплаты соискателей", "#a78bfa"):
                        ui.space()
                        el["combo_salary_role"] = ui.select(
                            options=role_options(),
                            value=None,
                            label="Роль",
                            with_input=True,
                            clearable=True,
                        ).props("dense outlined").style("width:160px").on(
                            "update:model-value", lambda e: c.handle_salary_role_change(e.args)
                        )
                        el["btn_collect_salary"] = ui.button(
                            "Собрать", icon="refresh",
                            on_click=c.handle_collect_salary_stats,
                        ).props("no-caps flat dense").classes("vob-btn-refresh")
                        el["btn_stop_salary"] = ui.button(
                            "Стоп", icon="stop",
                            on_click=c.handle_stop_salary_collect,
                        ).props("no-caps flat dense").classes("vob-btn-refresh").style(
                            "color:#f87171"
                        ).set_visibility(False)
                    el["salary_box"] = _scroll("gap-2")
                    with el["salary_box"]:
                        ui.label(
                            "Выберите роль и нажмите «Собрать» — "
                            "приложение просканирует резюме соискателей на hh.ru."
                        ).classes("italic vob-muted text-sm")
            with sp.after:
                with _card("h-full"):
                    with _section_head("leaderboard", "Топ навыков рынка", "#fb7a3c"):
                        ui.space()
                        el["combo_heatmap_n"] = ui.select(
                            {"10": "10", "20": "20", "30": "30"}, value="20", label="Топ",
                        ).props("dense outlined").style("width:90px")
                        ui.button(
                            "Обновить", icon="refresh", on_click=c.draw_skill_heatmap
                        ).props("no-caps flat dense").classes("vob-btn-refresh")
                    el["heatmap_box"] = _scroll("gap-2")
                    with el["heatmap_box"]:
                        ui.label(
                            "Нажмите «Построить», чтобы увидеть топ навыков."
                        ).classes("italic vob-muted")
