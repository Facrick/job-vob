"""Вкладка 5 — Учебник / план / упражнения."""
from nicegui import ui

from core.handbook import TRACKS
from gui_ng.views._shared import _card, _scroll, _split, _section_head


def build_handbook_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-0"):
        with _split(30) as sp:
            # ── Левая панель: навигация ────────────────────────────────
            with sp.before:
                with _card("h-full"):
                    el["hb_track"] = ui.select(
                        dict(TRACKS), value=getattr(c.handbook, "track", "qa"),
                        label="Направление",
                        on_change=lambda e: c.set_handbook_track(e.value),
                    ).props("dense outlined").classes("w-full")
                    el["hb_mode_toggle"] = ui.toggle(
                        {"sections": "Разделы", "favorites": "Избранное",
                         "plan": "План", "exercises": "Задания"},
                        value="sections",
                        on_change=lambda e: c.on_mode_toggle(e.value),
                    ).props(
                        "no-caps unelevated spread size=sm"
                    ).classes("w-full vob-hb-toggle")
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        el["hb_progress_label"] = ui.label("Прогресс 0% (0 из 0)").classes(
                            "text-xs vob-muted"
                        )
                    el["hb_progress"] = ui.linear_progress(value=0, show_value=False).props(
                        "color=primary"
                    )
                    el["hb_search"] = ui.input(
                        label="Поиск по темам"
                    ).props("dense outlined clearable").classes("w-full").on(
                        "input", lambda _: c.handle_handbook_search()
                    )
                    ui.button(
                        "Добавить тему", icon="add", on_click=c.handle_handbook_add_new
                    ).props("flat dense no-caps").classes("vob-btn-accent w-full")
                    el["hb_tree"] = _scroll("gap-1")

            # ── Правая панель: контент ─────────────────────────────────
            with sp.after:
                with _card("h-full"):
                    # Панель темы (просмотр / редактирование)
                    with ui.column().classes("w-full h-full no-wrap gap-2") as topic_pane:
                        el["hb_topic_pane"] = topic_pane
                        with ui.row().classes("w-full items-center gap-2"):
                            el["hb_topic_title"] = ui.label("").classes("text-base font-bold")
                            el["hb_topic_badge"] = ui.label("").classes("text-xs").style(
                                "color:#c4b5fd"
                            )
                            ui.space()
                            el["hb_btn_studied"] = ui.button(
                                icon="check_circle_outline", on_click=c.handle_handbook_studied
                            ).props("flat round dense").tooltip("Отметить изученным")
                            el["hb_btn_fav"] = ui.button(
                                icon="star_border", on_click=c.handle_handbook_favorite
                            ).props("flat round dense").tooltip("В избранное")
                            el["hb_btn_edit"] = ui.button(
                                "Редактировать", on_click=c.handle_handbook_edit
                            ).props("outline dense no-caps")
                        for k in ("hb_btn_studied", "hb_btn_fav", "hb_btn_edit"):
                            el[k].set_visibility(False)
                        el["hb_topic_divider"] = ui.separator()

                        # Режим просмотра
                        with _scroll() as view_box:
                            el["hb_view_box"] = view_box
                            with ui.column().classes(
                                "w-full h-full items-center justify-center gap-2"
                            ) as empty:
                                el["hb_empty"] = empty
                                ui.icon("menu_book", size="48px").classes("vob-muted")
                                ui.label(
                                    "Выберите тему слева, чтобы увидеть материал"
                                ).classes("vob-muted")
                            el["hb_answer"] = ui.markdown("")
                            el["hb_answer"].set_visibility(False)

                        # Режим редактирования
                        with ui.column().classes("w-full flex-grow no-wrap gap-2") as edit_box:
                            el["hb_edit_box"] = edit_box
                            el["hb_edit_title"] = ui.input(
                                label="Название темы"
                            ).props("dense outlined").classes("w-full")
                            el["hb_edit_title"].set_visibility(False)
                            el["hb_edit_section"] = ui.select(
                                {}, label="Раздел", new_value_mode="add-unique",
                            ).props("dense outlined").classes("w-full")
                            el["hb_edit_section"].set_visibility(False)
                            ui.label(
                                "Текст ответа (Markdown: ### заголовки, - списки, ``` код):"
                            ).classes("text-xs vob-muted")
                            el["hb_editor"] = ui.textarea().props("outlined").classes(
                                "w-full flex-grow vob-fill"
                            )
                            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                                el["hb_instr"] = ui.input(
                                    label="Что поправить? напр. «добавь пример кода»"
                                ).props("dense outlined").classes("flex-grow")
                                el["hb_btn_ai_fix"] = ui.button(
                                    "Поправить ИИ", icon="auto_awesome",
                                    on_click=c.handle_handbook_ai_fix,
                                ).props("outline no-caps")
                            with ui.row().classes("gap-2"):
                                ui.button(
                                    "Сохранить", icon="save", on_click=c.handle_handbook_save
                                ).props("no-caps flat").classes("vob-btn-accent")
                                ui.button(
                                    "Отмена", icon="close", on_click=c.handle_handbook_cancel
                                ).props("outline no-caps")
                        el["hb_edit_box"].set_visibility(False)

                    # Панель «План обучения»
                    with ui.column().classes("w-full h-full no-wrap gap-2") as plan_box:
                        el["hb_plan_box"] = plan_box
                        _section_head("checklist", "План обучения", "#a78bfa")
                        ui.separator()
                        el["hb_plan_list"] = _scroll("gap-1")
                    el["hb_plan_box"].set_visibility(False)

                    # Панель «Упражнения»
                    with ui.column().classes("w-full h-full no-wrap gap-2") as ex_box:
                        el["hb_exercise_box"] = ex_box
                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            with ui.element("div").classes("vob-sec-icon").style("--vob-accent:#fb7a3c"):
                                ui.icon("fitness_center")
                            el["ex_topic_label"] = ui.label("Упражнения").classes(
                                "text-base font-bold truncate"
                            )
                            ui.space()
                            el["ex_progress"] = ui.badge("").classes("text-xs")
                            el["ex_progress"].set_visibility(False)
                            el["ex_spinner"] = ui.spinner(size="sm")
                            el["ex_spinner"].set_visibility(False)
                            el["ex_btn_new"] = ui.button(
                                "Другое задание", icon="casino",
                                on_click=c.handle_exercise_new,
                            ).props("outline dense no-caps")
                            el["ex_btn_new"].set_visibility(False)
                        ui.separator()
                        with _scroll("gap-2"):
                            with ui.column().classes(
                                "w-full h-full items-center justify-center gap-2"
                            ) as ex_empty:
                                el["ex_empty"] = ex_empty
                                ui.icon("fitness_center", size="48px").classes("vob-muted")
                                ui.label(
                                    "Выберите тему слева, чтобы получить практическое задание"
                                ).classes("vob-muted text-center")
                            with ui.column().classes("w-full no-wrap gap-2") as ex_content:
                                el["ex_content"] = ex_content
                                el["ex_task"] = ui.markdown("")
                                el["ex_answer"] = ui.textarea(
                                    label="Ваше решение"
                                ).props("outlined autogrow").classes("w-full")
                                with ui.row().classes("gap-2"):
                                    el["ex_btn_check"] = ui.button(
                                        "Проверить", icon="task_alt",
                                        on_click=c.handle_exercise_check,
                                    ).props("no-caps flat").classes("vob-btn-accent")
                                with ui.column().classes("w-full no-wrap gap-1") as ex_result:
                                    el["ex_result"] = ex_result
                                    with ui.row().classes("items-center gap-2"):
                                        el["ex_score_badge"] = ui.badge("").classes("text-sm")
                                    el["ex_feedback"] = ui.markdown("")
                                el["ex_result"].set_visibility(False)
                            el["ex_content"].set_visibility(False)
                    el["hb_exercise_box"].set_visibility(False)
