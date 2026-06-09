"""Вкладка 1 — CRM / Поиск вакансий."""
from nicegui import ui

from gui_ng.views._shared import _card, _scroll, _split


def build_scout_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        # Панель фильтров
        with _card():
            with ui.row().classes("items-center w-full gap-2"):
                ui.icon("travel_explore", color="primary")
                ui.label("Поиск вакансий на hh.ru").classes("text-base font-semibold")
                ui.button(icon="expand_less", on_click=c.toggle_filters).props(
                    "flat round dense"
                ).tooltip("Свернуть/развернуть фильтры")
                ui.space()
                el["resume_label"] = ui.label("").classes("text-xs vob-muted")
                # ── Индикатор авторизации hh.ru ───────────────────────────
                el["hh_auth_badge"] = ui.label("⬤  hh.ru …").style(
                    "font-size:11px;font-weight:600;letter-spacing:.02em;"
                    "padding:3px 8px;border-radius:6px;cursor:default;"
                    "color:#71717a;background:#27272a;border:1px solid #3f3f46"
                ).tooltip("Статус авторизации на hh.ru")
                el["btn_hh_login"] = ui.button(
                    "Войти", icon="login", on_click=c.handle_hh_login
                ).props("flat no-caps dense").style(
                    "font-size:12px;color:#a78bfa"
                ).tooltip("Открыть браузер для входа на hh.ru")
                el["btn_hh_login"].set_visibility(False)
                ui.button(
                    icon="refresh", on_click=c.recheck_hh_auth
                ).props("flat round dense").style("color:#52525b").tooltip(
                    "Перепроверить статус авторизации hh.ru"
                )
                el["btn_resume"] = ui.button(
                    "Резюме", icon="upload_file", on_click=c.handle_resume_upload
                ).props("outline no-caps").tooltip("Загрузить PDF-резюме")
                el["btn_hh_sync"] = ui.button(
                    "Синх. hh.ru", icon="sync", on_click=c.handle_hh_sync
                ).props("outline no-caps").tooltip(
                    "Обновить статусы вакансий по данным hh.ru"
                )
                el["toggle_autosync"] = ui.switch(
                    "Авто", on_change=c.handle_autosync_toggle
                ).tooltip("Автоматически синхронизировать статусы раз в час").classes("text-xs")
                el["btn_export"] = ui.button(
                    "Экспорт CSV", icon="download", on_click=c.handle_export
                ).props("outline no-caps").tooltip("Выгрузить воронку в CSV")

            with ui.column().classes("w-full gap-2") as filters:
                el["filters_row"] = filters
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    el["input_keyword"] = ui.input(
                        "Ключевое слово", value="QA Engineer"
                    ).props("dense outlined").classes("flex-grow").on(
                        "keydown.enter", c.handle_search
                    )
                    el["toggle_expand"] = ui.checkbox(
                        "Расширенный", value=False,
                    ).tooltip(
                        "Искать также по синонимам: тестировщик, AQA, SDET, "
                        "инженер по тестированию и др."
                    ).classes("text-sm no-wrap").style("color:#a1a1aa")
                    el["btn_search"] = ui.button(
                        "Найти", icon="search", on_click=c.handle_search
                    ).props("no-caps")
                with ui.element("div").classes("w-full").style(
                    "display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px"
                ):
                    el["combo_period"] = ui.select(
                        {"1": "За сутки", "3": "За 3 дня", "7": "За неделю", "30": "За месяц"},
                        value="7", label="Период",
                    ).props("dense outlined")
                    el["combo_exp"] = ui.select(
                        {"noExperience": "Без опыта", "between1And3": "1–3 года",
                         "between3And6": "3–6 лет", "moreThan6": "Более 6 лет"},
                        value="between1And3", label="Опыт",
                    ).props("dense outlined")
                    el["combo_schedule"] = ui.select(
                        {"remote": "Удалённая", "fullDay": "Полный день", "flexible": "Гибкий",
                         "shift": "Вахта", "": "Все форматы"},
                        value="remote", label="Формат",
                    ).props("dense outlined")
                    el["combo_area"] = ui.select(
                        {"113": "Вся Россия", "1": "Москва", "2": "Санкт-Петербург"},
                        value="113", label="Регион",
                    ).props("dense outlined")
                    el["status_filter"] = ui.select(
                        {"all": "Вся воронка", "discovered": "Новые",
                         "processed": "Письмо готово", "applied": "Отклик отправлен",
                         "interview": "Собеседование", "offer": "Оффер!", "rejected": "Отказ"},
                        value="all", label="Этап воронки",
                        on_change=lambda _: c.refresh_table_data(),
                    ).props("dense outlined")
                    el["salary_exp"] = ui.input(
                        "Ожидаемая з/п, ₽", placeholder="напр. 150000",
                    ).props("dense outlined").on(
                        "blur", lambda _: c.handle_salary_expectation_change()
                    )
            el["search_status"] = ui.label("").classes("text-xs vob-muted")
            el["search_status"].set_visibility(False)
            el["search_progress"] = ui.linear_progress(value=0, show_value=False).props(
                "color=primary"
            )
            el["search_progress"].set_visibility(False)
            el["funnel_counters"] = ui.row().classes("gap-2 flex-wrap items-center")
            with ui.row().classes("items-center gap-2 w-full"):
                el["crm_search"] = ui.input(
                    placeholder="🔍  Поиск по названию / компании…"
                ).props("dense outlined clearable").classes("flex-grow").on(
                    "update:model-value", lambda _: c.handle_crm_search()
                )

        # Панель bulk-действий (скрыта пока нет выделения)
        with ui.row().classes("items-center gap-2 w-full") as bulk_bar:
            el["bulk_bar"] = bulk_bar
            ui.icon("checklist", color="primary")
            el["bulk_count_label"] = ui.label("").classes("text-sm font-semibold").style(
                "color:#e4e4e7"
            )
            el["bulk_status_select"] = ui.select(
                {"discovered": "Новая", "processed": "Письмо готово",
                 "applied": "Отклик отправлен", "interview": "Собеседование",
                 "offer": "Оффер!", "rejected": "Отказ"},
                label="Новый статус",
            ).props("dense outlined").classes("w-48")
            ui.button(
                "Применить", icon="done_all", on_click=c.handle_bulk_status
            ).props("no-caps dense")
            ui.button(
                "Удалить", icon="delete_outline", on_click=c.handle_bulk_delete
            ).props("outline no-caps dense color=negative")
            ui.space()
            ui.button(
                "Снять выделение", icon="deselect", on_click=c.handle_bulk_deselect
            ).props("flat no-caps dense").style("color:#71717a")
        bulk_bar.set_visibility(False)

        # Таблица + детали
        with _split(58) as sp:
            with sp.before:
                with _card("h-full"):
                    columns = [
                        {"name": "match", "label": "Match", "field": "match_num",
                         "align": "center", "sortable": True, "sort": "desc",
                         "headerStyle": "width:70px"},
                        {"name": "company", "label": "Компания", "field": "company",
                         "align": "left", "sortable": True, "headerStyle": "width:150px"},
                        {"name": "title", "label": "Вакансия", "field": "title",
                         "align": "left", "sortable": True, "headerStyle": "width:230px"},
                        {"name": "salary", "label": "З/п", "field": "salary_num",
                         "align": "left", "sortable": True, "headerStyle": "width:120px"},
                        {"name": "status", "label": "Статус", "field": "status_num",
                         "align": "center", "sortable": True, "headerStyle": "width:96px"},
                    ]
                    table = ui.table(columns=columns, rows=[], row_key="id").classes(
                        "w-full h-full vob-table"
                    )
                    table.props("flat dense :rows-per-page-options=[0] selection=multiple")
                    table.on("update:selected", c.handle_bulk_selection_change)
                    table.add_slot("body-cell-match", """
                        <q-td :props="props">
                          <q-badge :style="'background:'+props.row.match_color+'40'+';color:#fff;border:1px solid '+props.row.match_color+';font-weight:700;min-width:38px;text-align:center'">{{ props.row.match }}</q-badge>
                        </q-td>
                    """)
                    table.add_slot("body-cell-salary", """
                        <q-td :props="props">
                          <span :style="'color:'+props.row.salary_color">{{ props.row.salary }}</span>
                        </q-td>
                    """)
                    table.add_slot("body-cell-status", """
                        <q-td :props="props">
                          <q-badge :style="'background:'+props.row.status_color+'33'+';color:#fff;border:1px solid '+props.row.status_color+'88;font-weight:600'">{{ props.row.status }}</q-badge>
                        </q-td>
                    """)
                    table.on("rowClick", c.on_row_click)
                    el["table"] = table

            with sp.after:
                with _card("h-full"):
                    el["detail_title"] = ui.label("Вакансия не выбрана").classes(
                        "text-lg font-bold"
                    )
                    el["detail_meta"] = ui.label(
                        "Кликните строку в таблице слева, чтобы увидеть подробности."
                    ).classes("vob-muted")
                    el["detail_status"] = ui.select(
                        {"discovered": "Новая", "processed": "Письмо готово",
                         "applied": "Отклик отправлен", "interview": "Собеседование",
                         "offer": "Оффер!", "rejected": "Отказ"},
                        label="Этап воронки", on_change=c.handle_status_change,
                    ).props("dense outlined").classes("w-full")
                    el["detail_status"].set_visibility(False)
                    with ui.row().classes("gap-2 flex-wrap"):
                        el["btn_generate"] = ui.button(
                            "ИИ-письмо", icon="auto_awesome", on_click=c.handle_generation
                        ).props("no-caps")
                        el["btn_analyze"] = ui.button(
                            "Анализ ИИ", icon="insights", on_click=c.handle_analyze
                        ).props("outline no-caps")
                        el["btn_open_url"] = ui.button(
                            "hh.ru", icon="open_in_new", on_click=c.open_vacancy_in_browser
                        ).props("outline no-caps")
                        el["btn_delete_vacancy"] = ui.button(
                            icon="delete_outline", on_click=c.handle_delete_vacancy
                        ).props("outline no-caps color=negative").tooltip("Удалить вакансию")
                    for k in ("btn_generate", "btn_analyze", "btn_open_url", "btn_delete_vacancy"):
                        el[k].set_visibility(False)
                    ui.separator()
                    with _scroll():
                        ui.label("Ключевые навыки").classes("text-sm font-semibold")
                        el["detail_skills"] = ui.label("—").classes("text-sm")
                        ui.label("Описание").classes("text-sm font-semibold mt-2")
                        el["detail_description"] = ui.html("").classes(
                            "vob-vacancy-desc text-sm w-full"
                        )
                        ui.label("HR / Контакты").classes("text-sm font-semibold mt-2")
                        with ui.column().classes("gap-1 w-full"):
                            el["detail_hr_name"] = ui.input(
                                label="Имя HR", placeholder="Иванова Анна"
                            ).props("dense outlined").classes("w-full").on(
                                "blur", lambda _: c.handle_hr_details_save()
                            )
                            el["detail_contacts"] = ui.input(
                                label="Контакты", placeholder="t.me/anna, +7 999 …"
                            ).props("dense outlined").classes("w-full").on(
                                "blur", lambda _: c.handle_hr_details_save()
                            )
                            el["detail_interview_date"] = ui.input(
                                label="Дата собеседования", placeholder="2026-06-20 15:00"
                            ).props("dense outlined").classes("w-full").on(
                                "blur", lambda _: c.handle_hr_details_save()
                            )
                        ui.label("Заметки").classes("text-sm font-semibold mt-2")
                        el["detail_notes"] = ui.textarea(
                            placeholder="Личные заметки по вакансии..."
                        ).props("dense outlined autogrow").classes("w-full").on(
                            "blur", lambda _: c.handle_notes_save()
                        )
                        ui.label("Анализ ИИ").classes("text-sm font-semibold mt-2")
                        el["detail_analysis"] = ui.markdown("")
                        ui.label("Чему подучиться").classes("text-sm font-semibold mt-2")
                        el["detail_gaps"] = ui.column().classes("gap-1 w-full")
