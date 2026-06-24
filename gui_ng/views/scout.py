"""Вкладка CRM — список вакансий, воронка, поиск."""
from nicegui import ui

from gui_ng.theme import STATUS_STYLE
from gui_ng.views._shared import _card, _scroll, _metric_card
from gui_ng.views._vacancy_list import VacancyList
from gui_ng.views._filter_chip import FilterChip

# Цвета берём из единой статусной палитры темы (STATUS_STYLE), чтобы KPI-карточки
# звучали в тон бейджам таблицы и воронке. «Всего» — нейтральный синий (агрегат).
_s = STATUS_STYLE
_FUNNEL_METRICS = [
    ("total",      "Всего",         "layers",          "#60a5fa"),
    ("discovered", "Новые",         "auto_awesome",    _s["discovered"][1]),
    ("processed",  "Письмо",        "description",     _s["processed"][1]),
    ("applied",    "Отклик",        "send",            _s["applied"][1]),
    ("interview",  "Собеседование", "event_available", _s["interview"][1]),
    ("offer",      "Оффер",         "celebration",     _s["offer"][1]),
    ("rejected",   "Отказ",         "cancel",          _s["rejected"][1]),
]


def build_scout_tab(c):
    el = c.el

    with ui.element("div").classes("vob-crm-root"):

        # ── KPI-карточки ──────────────────────────────────────────────
        with ui.element("div").classes("vob-crm-kpi-row"):
            el["funnel_metrics"] = {}
            for key, label, icon, accent in _FUNNEL_METRICS:
                val, _ = _metric_card(label, "0", icon, accent)
                el["funnel_metrics"][key] = val

        # ── Панель поиска и фильтров ───────────────────────────────────
        with ui.element("div").classes("vob-search-panel"):

            # Строка 1: поле поиска должности + кнопка Найти + статус hh
            with ui.element("div").classes("vob-search-row"):
                with ui.element("div").classes("vob-search-field-wrap"):
                    ui.html('<span class="material-icons vob-search-icon">search</span>')
                    from core.synonyms import role_options
                    el["input_keyword"] = ui.select(
                        options=role_options(),
                        label=None,
                        with_input=True,
                        new_value_mode="add-unique",
                        clearable=True,
                    ).props('dense borderless input-debounce="0" placeholder="Должность / роль"').classes(
                        "vob-search-input"
                    ).on("keydown.enter", c.handle_search)

                el["btn_search"] = ui.button(
                    "Найти", icon="search", on_click=c.handle_search
                ).props("no-caps flat").classes("vob-search-btn vob-btn-accent")
                el["btn_stop_search"] = ui.button(
                    "Стоп", icon="stop", on_click=c.handle_stop_search
                ).props("no-caps color=negative").classes("vob-search-btn")
                el["btn_stop_search"].set_visibility(False)

                with ui.element("div").classes("vob-search-divider"): pass

                el["hh_auth_badge"] = ui.label("⬤").classes("vob-auth-dot").tooltip(
                    "hh.ru: статус авторизации"
                )
                el["btn_hh_login"] = ui.button(
                    "Войти в hh.ru", icon="login", on_click=c.handle_hh_login
                ).props("flat no-caps dense").classes("vob-btn-link")
                el["btn_hh_login"].set_visibility(False)

                el["btn_hh_sync"] = ui.button(
                    "Синх. hh.ru", icon="sync", on_click=c.handle_hh_sync
                ).props("flat no-caps dense").classes(
                    "vob-btn-refresh vob-btn-refresh--tall"
                ).tooltip("Синхронизировать статусы с hh.ru")

                el["resume_label"] = ui.label("").classes("vob-muted text-xs")
                el["resume_label"].set_visibility(False)

            # Строка 2: чипы-фильтры
            with ui.element("div").classes("vob-filters-row"):
                el["combo_period"] = FilterChip(
                    "Период",
                    {"1": "За сутки", "3": "За 3 дня", "7": "За неделю", "30": "За месяц"},
                    default="7",
                )
                el["combo_exp"] = FilterChip(
                    "Опыт",
                    {"noExperience": "Без опыта", "between1And3": "1–3 года",
                     "between3And6": "3–6 лет", "moreThan6": "Более 6 лет"},
                    default=[],
                    multiple=True,
                )
                el["combo_schedule"] = FilterChip(
                    "Формат",
                    {"remote": "Удалённо", "fullDay": "Офис", "flexible": "Гибрид"},
                    default=[],
                    multiple=True,
                )
                el["combo_area"] = FilterChip(
                    "Регион",
                    {
                        "0": "Все страны", "113": "Вся Россия",
                        "40": "Казахстан", "16": "Беларусь", "97": "Узбекистан",
                        "48": "Кыргызстан", "9": "Азербайджан", "13": "Армения",
                        "1": "Москва", "2": "Санкт-Петербург", "3": "Екатеринбург",
                        "4": "Новосибирск", "88": "Казань", "66": "Нижний Новгород",
                        "78": "Самара", "76": "Ростов-на-Дону", "68": "Омск",
                        "53": "Краснодар", "99": "Уфа", "72": "Пермь",
                        "26": "Воронеж", "54": "Красноярск",
                    },
                    default="113",
                )
                el["status_filter"] = FilterChip(
                    "Этап",
                    {"all": "Вся воронка", "discovered": "Новые",
                     "processed": "Письмо", "applied": "Отклик",
                     "interview": "Собеседование", "offer": "Оффер", "rejected": "Отказ"},
                    default="all",
                    on_change=lambda: c.refresh_table_data(),
                )
                el["salary_exp"] = ui.input("З/п от, ₽").props("dense outlined").classes(
                    "vob-filter-salary-input"
                ).on("blur", lambda _: c.handle_salary_expectation_change())
                el["crm_search"] = ui.input(
                    placeholder="Название, компания…"
                ).props("dense outlined clearable").classes("vob-filter-search-input").on(
                    "update:model-value", lambda _: c.handle_crm_search()
                )

            # Прогресс поиска — отдельная статус-строка в нижней части панели
            with ui.element("div").classes("vob-search-statusbar"):
                el["search_status"] = ui.label("").classes("text-xs vob-muted")
                el["search_status"].set_visibility(False)
                el["search_progress"] = ui.linear_progress(
                    value=0, show_value=False
                ).props("color=primary").classes("vob-search-progress")
                el["search_progress"].set_visibility(False)

        # ── Bulk-панель ────────────────────────────────────────────────
        with ui.element("div").classes("vob-bulk-bar") as bulk_bar:
            el["bulk_bar"] = bulk_bar
            with ui.element("div").classes("vob-bulk-inner"):
                ui.html('<span class="material-icons" style="color:#a78bfa;font-size:18px">checklist</span>')
                el["bulk_count_label"] = ui.label("").classes("vob-bulk-count")
                with ui.element("div").classes("vob-bulk-div"): pass
                ui.label("Статус:").classes("text-xs vob-muted")
                el["bulk_status_select"] = ui.select(
                    {"discovered": "Новая", "processed": "Письмо",
                     "applied": "Отклик", "interview": "Собеседование",
                     "offer": "Оффер", "rejected": "Отказ"},
                    label=None,
                ).props("dense outlined").classes("vob-bulk-select")
                ui.button("Применить", icon="done_all", on_click=c.handle_bulk_status).props(
                    "no-caps dense color=primary"
                )
                with ui.element("div").classes("vob-bulk-div"): pass
                ui.button(
                    "Удалить", icon="delete_outline", on_click=c.handle_bulk_delete
                ).props("outline no-caps dense color=negative")
                ui.button(
                    "Снять", icon="close", on_click=c.handle_bulk_deselect
                ).props("flat no-caps dense").classes("vob-muted")
        bulk_bar.set_visibility(False)

        # ── Таблица (на всю ширину) + drawer деталей ──────────────────
        with ui.element("div").classes("vob-crm-body"):
            with ui.element("div").classes("vob-table-card"):
                with ui.element("div").classes("vob-table-header"):
                    ui.html('<span class="material-icons" style="font-size:16px;color:#a78bfa">table_rows</span>')
                    el["table_title"] = ui.label("Вакансии").classes("vob-table-title")
                el["table"] = VacancyList(
                    on_row_click=c.on_row_click,
                    on_selection_change=c.handle_bulk_selection_change,
                )

            # Drawer деталей вакансии
            with ui.element("div").classes("vob-drawer") as drawer:
                el["detail_drawer"] = drawer
                # Шапка drawer
                with ui.element("div").classes("vob-drawer-head"):
                    with ui.element("div").classes("vob-drawer-titles"):
                        el["detail_title"] = ui.label("Вакансия не выбрана").classes(
                            "vob-drawer-title"
                        )
                        el["detail_meta"] = ui.label("").classes("vob-drawer-meta vob-muted")
                    with ui.element("div").classes("vob-drawer-close-btn").on(
                        "click", lambda _: c.close_detail()
                    ):
                        ui.html('<span class="material-icons" style="font-size:20px;color:#71717a">close</span>')

                # Статус + кнопки
                with ui.element("div").classes("vob-drawer-actions"):
                    el["detail_status"] = ui.select(
                        {"discovered": "Новая", "processed": "Письмо готово",
                         "applied": "Отклик отправлен", "interview": "Собеседование",
                         "offer": "Оффер!", "rejected": "Отказ"},
                        label="Этап воронки", on_change=c.handle_status_change,
                    ).props("dense outlined").classes("vob-drawer-status")
                    el["detail_status"].set_visibility(False)
                    with ui.element("div").classes("vob-drawer-btns"):
                        el["btn_generate"] = ui.button(
                            "ИИ-письмо", icon="auto_awesome", on_click=c.handle_generation
                        ).props("no-caps")
                        el["btn_analyze"] = ui.button(
                            "Анализ", icon="insights", on_click=c.handle_analyze
                        ).props("outline no-caps")
                        el["btn_open_url"] = ui.button(
                            "hh.ru", icon="open_in_new", on_click=c.open_vacancy_in_browser
                        ).props("outline no-caps")
                        el["btn_delete_vacancy"] = ui.button(
                            icon="delete_outline", on_click=c.handle_delete_vacancy
                        ).props("outline no-caps color=negative").classes(
                            "vob-drawer-del"
                        ).tooltip("Удалить")
                        el["btn_auto_apply"] = ui.button(
                            "Откликнуться", icon="send", on_click=c.handle_auto_apply
                        ).props("outline no-caps").tooltip("Автоматически откликнуться через hh.ru")
                    for k in ("btn_generate", "btn_analyze", "btn_open_url",
                              "btn_delete_vacancy", "btn_auto_apply"):
                        el[k].set_visibility(False)

                # Тело drawer
                with ui.element("div").classes("vob-drawer-body"):
                    with _scroll():
                        ui.label("Ключевые навыки").classes("vob-detail-section")
                        el["detail_skills"] = ui.label("—").classes("text-sm")
                        ui.label("Описание").classes("vob-detail-section")
                        el["detail_description"] = ui.html("").classes(
                            "vob-vacancy-desc text-sm w-full"
                        )
                        ui.label("HR / Контакты").classes("vob-detail-section")
                        with ui.column().classes("gap-1 w-full"):
                            el["detail_hr_name"] = ui.input("Имя HR").props(
                                "dense outlined"
                            ).classes("w-full").on("blur", lambda _: c.handle_hr_details_save())
                            el["detail_contacts"] = ui.input("Контакты").props(
                                "dense outlined"
                            ).classes("w-full").on("blur", lambda _: c.handle_hr_details_save())
                            el["detail_interview_date"] = ui.input("Дата собеседования").props(
                                "dense outlined"
                            ).classes("w-full").on("blur", lambda _: c.handle_hr_details_save())
                        ui.label("Заметки").classes("vob-detail-section")
                        el["detail_notes"] = ui.textarea(
                            label="Личные заметки"
                        ).props("dense outlined autogrow").classes("w-full").on(
                            "blur", lambda _: c.handle_notes_save()
                        )
                        ui.label("Анализ ИИ").classes("vob-detail-section")
                        el["detail_analysis"] = ui.markdown("")
                        ui.label("Чему подучиться").classes("vob-detail-section")
                        el["detail_gaps"] = ui.column().classes("gap-1 w-full")

            drawer.set_visibility(False)
