"""views.py — построение UI вкладок для NiceGUI-версии.

Каждая build_*_tab(c) создаёт элементы и кладёт их в c.el[...], откуда контроллер
читает значения и обновляет содержимое. Бизнес-логики здесь нет.

Двухпанельные вкладки используют ui.splitter — разделитель (с грипом по центру)
перетаскивается мышью, панели меняют размер.
"""

from nicegui import ui

from core.handbook import TRACKS


def _card(extra=""):
    """Карточка-контейнер: flex-колонка, не переносит контент, со скруглением.

    overflow-hidden гарантирует, что внутреннее переполнение прокручивает только
    вложенный .vob-scroll, а не сама карточка/панель (иначе появляются лишние скроллы).
    """
    return ui.card().classes(f"w-full no-wrap overflow-hidden {extra}").props(
        "flat bordered"
    )


def _scroll(extra=""):
    """Прокручиваемая колонка: полоса появляется только при переполнении."""
    return ui.column().classes(f"w-full vob-scroll {extra}").style(
        "flex:1 1 0;min-height:0"
    )


def _split(value=58):
    """Горизонтальный сплиттер с грипом, заполняющий высоту вкладки."""
    sp = ui.splitter(value=value).classes("w-full").style("flex:1 1 0;min-height:0")
    with sp.separator:
        ui.element("div").classes("vob-grip")
    return sp


# ──────────────────────────────────────────────────────────────
#  Вкладка 1 — CRM / поиск
# ──────────────────────────────────────────────────────────────
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
                el["btn_resume"] = ui.button(
                    "Резюме", icon="upload_file", on_click=c.handle_resume_upload
                ).props("outline no-caps").tooltip("Загрузить PDF-резюме")
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
                        {"all": "Вся воронка", "discovered": "Новые", "processed": "Письмо готово",
                         "applied": "Отклик отправлен", "interview": "Собеседование",
                         "offer": "Оффер!", "rejected": "Отказ"},
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

        # Таблица + детали (перетаскиваемый разделитель)
        with _split(58) as sp:
            with sp.before:
                with _card("h-full"):
                    # headerStyle задаёт стартовую ширину колонки (<th>); при table-layout:fixed
                    # её можно тянуть мышью (ресайзер в theme.py), а текст обрезается по «…».
                    columns = [
                        {"name": "match", "label": "Match", "field": "match",
                         "align": "center", "headerStyle": "width:70px"},
                        {"name": "company", "label": "Компания", "field": "company",
                         "align": "left", "sortable": True, "headerStyle": "width:150px"},
                        {"name": "title", "label": "Вакансия", "field": "title",
                         "align": "left", "sortable": True, "headerStyle": "width:230px"},
                        {"name": "salary", "label": "З/п", "field": "salary",
                         "align": "left", "headerStyle": "width:120px"},
                        {"name": "status", "label": "Статус", "field": "status",
                         "align": "center", "headerStyle": "width:96px"},
                    ]
                    table = ui.table(columns=columns, rows=[], row_key="id").classes(
                        "w-full h-full vob-table"
                    )
                    table.props("flat dense :rows-per-page-options=[0]")
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
                    for k in ("btn_generate", "btn_analyze", "btn_open_url"):
                        el[k].set_visibility(False)
                    ui.separator()
                    with _scroll():
                        ui.label("Ключевые навыки").classes("text-sm font-semibold")
                        el["detail_skills"] = ui.label("—").classes("text-sm")
                        ui.label("Описание").classes("text-sm font-semibold mt-2")
                        el["detail_description"] = ui.html("").classes(
                            "vob-vacancy-desc text-sm w-full"
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


# ──────────────────────────────────────────────────────────────
#  Вкладка 2 — Письма
# ──────────────────────────────────────────────────────────────
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


# ──────────────────────────────────────────────────────────────
#  Вкладка 3 — Mock-собеседование
# ──────────────────────────────────────────────────────────────
def build_interview_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                ui.icon("psychology", color="primary")
                ui.label("Mock-собеседование с ИИ").classes("text-base font-semibold")
                el["combo_format"] = ui.select(
                    {"tech": "Техническое", "hr": "HR-скрининг",
                     "system_design": "System Design", "behavioral": "Поведенческое (STAR)"},
                    value="tech", label="Формат",
                ).props("dense outlined").classes("ml-4").style("min-width:180px")
                ui.space()
                el["btn_start"] = ui.button(
                    "Начать", icon="play_arrow", on_click=c.handle_start_mock
                ).props("no-caps")
                el["btn_evaluate"] = ui.button(
                    "Оценить сессию", icon="assessment", on_click=c.handle_evaluate_interview
                ).props("outline no-caps")
                el["btn_evaluate"].set_visibility(False)
                el["btn_reset"] = ui.button(
                    "Сбросить", icon="refresh", on_click=c.handle_reset_mock
                ).props("outline no-caps")
            el["interview_vacancy_label"] = ui.label("Вакансия не выбрана").classes(
                "text-xs vob-muted italic"
            )
        with _split(60) as sp:
            with sp.before:
                with _card("h-full"):
                    el["chat_arena"] = _scroll("gap-2")
            with sp.after:
                with _card("h-full"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("assessment", color="primary")
                        ui.label("Отчёт по сессии").classes("text-base font-semibold")
                    el["report_box"] = _scroll("gap-2")
                    with el["report_box"]:
                        ui.label("Завершите сессию и нажмите «Оценить сессию»").classes(
                            "italic vob-muted text-sm"
                        )
        with _card():
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                el["input_chat"] = ui.input("Ваш ответ...").props(
                    "dense outlined"
                ).classes("flex-grow").on("keydown.enter", c.handle_send_chat)
                el["btn_send"] = ui.button(
                    "Отправить", icon="send", on_click=c.handle_send_chat
                ).props("no-caps")


# ──────────────────────────────────────────────────────────────
#  Вкладка 4 — Аналитика
# ──────────────────────────────────────────────────────────────
def build_analytics_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-3"):
        with _card():
            with ui.row().classes("items-center gap-2"):
                ui.icon("filter_alt", color="primary")
                ui.label("Воронка поиска работы").classes("text-base font-semibold")
            el["funnel_box"] = ui.column().classes("w-full gap-3")
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


# ──────────────────────────────────────────────────────────────
#  Вкладка 5 — Учебник
# ──────────────────────────────────────────────────────────────
def build_handbook_tab(c):
    el = c.el
    with ui.column().classes("w-full h-full no-wrap gap-0"):
        with _split(30) as sp:
            # Левая панель
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
                        "no-caps unelevated spread toggle-color=primary size=sm"
                    ).classes("w-full")
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        el["hb_progress_label"] = ui.label("Прогресс 0% (0 из 0)").classes(
                            "text-xs vob-muted"
                        )
                    el["hb_progress"] = ui.linear_progress(value=0, show_value=False).props(
                        "color=positive"
                    )
                    el["hb_search"] = ui.input(
                        placeholder="Поиск по темам..."
                    ).props("dense outlined clearable").classes("w-full").on(
                        "input", lambda _: c.handle_handbook_search()
                    )
                    ui.button(
                        "Добавить тему", icon="add", on_click=c.handle_handbook_add_new
                    ).props("outline dense no-caps").classes("w-full")
                    el["hb_tree"] = _scroll("gap-1")

            # Правая панель
            with sp.after:
                with _card("h-full"):
                    # Панель темы
                    with ui.column().classes("w-full h-full no-wrap gap-2") as topic_pane:
                        el["hb_topic_pane"] = topic_pane
                        with ui.row().classes("w-full items-center gap-2"):
                            el["hb_topic_title"] = ui.label("").classes("text-base font-bold")
                            el["hb_topic_badge"] = ui.label("").classes("text-xs").style(
                                "color:#ffca28"
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
                                    placeholder="Что поправить? напр. «добавь пример кода»"
                                ).props("dense outlined").classes("flex-grow")
                                el["hb_btn_ai_fix"] = ui.button(
                                    "Поправить ИИ", icon="auto_awesome",
                                    on_click=c.handle_handbook_ai_fix,
                                ).props("outline no-caps")
                            with ui.row().classes("gap-2"):
                                ui.button(
                                    "Сохранить", icon="save", on_click=c.handle_handbook_save
                                ).props("no-caps")
                                ui.button(
                                    "Отмена", icon="close", on_click=c.handle_handbook_cancel
                                ).props("outline no-caps")
                        el["hb_edit_box"].set_visibility(False)

                    # Панель «План обучения» (показывается в режиме «План»).
                    with ui.column().classes("w-full h-full no-wrap gap-2") as plan_box:
                        el["hb_plan_box"] = plan_box
                        with ui.row().classes("w-full items-center gap-2"):
                            ui.icon("checklist", color="primary")
                            ui.label("План обучения").classes("text-base font-bold")
                        ui.separator()
                        el["hb_plan_list"] = _scroll("gap-1")
                    el["hb_plan_box"].set_visibility(False)

                    # Панель «Упражнения» (режим «Задания»): задание по выбранной теме,
                    # ответ ученика и проверка ИИ по скрытому эталону.
                    with ui.column().classes("w-full h-full no-wrap gap-2") as ex_box:
                        el["hb_exercise_box"] = ex_box
                        with ui.row().classes("w-full items-center gap-2 no-wrap"):
                            ui.icon("fitness_center", color="primary")
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
                                    ).props("no-caps")
                                # Блок результата проверки.
                                with ui.column().classes("w-full no-wrap gap-1") as ex_result:
                                    el["ex_result"] = ex_result
                                    with ui.row().classes("items-center gap-2"):
                                        el["ex_score_badge"] = ui.badge("").classes("text-sm")
                                    el["ex_feedback"] = ui.markdown("")
                                el["ex_result"].set_visibility(False)
                            el["ex_content"].set_visibility(False)
                    el["hb_exercise_box"].set_visibility(False)


# ──────────────────────────────────────────────────────────────
#  Вкладка 6 — Логи
# ──────────────────────────────────────────────────────────────
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
        el["logs"] = ui.log().classes("w-full flex-grow").style(
            "font-family:Consolas,monospace;font-size:12px"
        )
