"""flet_views.py — UI для Flet 0.85+

Дизайн: тёмная тема, карточки, единый стиль кнопок, шапка + NavigationBar снизу.

Layout-правила (проверено эмпирически):
  • НЕ ставить expand=True у ребёнка внутри Row(wrap=True)  → серый экран.
  • НЕ ставить expand=True у ребёнка внутри scroll-контейнера → серый экран.
  • НЕ класть Row внутрь Row(wrap=True) → серый экран.
  • Прокрутка — через ListView/Row/Column(scroll=AUTO).
  • Виджеты, у которых меняется видимость/состояние, создавать в __init__
    (персистентны), чтобы переживать ресайз и смену вкладки.
"""
import flet as ft

# ── Палитра ───────────────────────────────────────────────────
ACCENT      = ft.Colors.INDIGO_300
CARD_BG     = ft.Colors.SURFACE_CONTAINER_HIGH
CARD_RADIUS = 14
GAP         = 12
# Ниже этой ширины окна двухпанельные вкладки складываются вертикально.
BREAKPOINT  = 860


# ── Переиспользуемые компоненты ──────────────────────────────
def primary_btn(text, on_click, icon=None, bgcolor=None, color=None, expand=False, width=None):
    return ft.FilledButton(content=text, on_click=on_click, icon=icon,
                           bgcolor=bgcolor, color=color, expand=expand, width=width, height=42)


def secondary_btn(text, on_click, icon=None, expand=False):
    return ft.OutlinedButton(content=text, on_click=on_click, icon=icon, expand=expand, height=42)


def card(content, *, expand=False, padding=16):
    return ft.Container(content=content, bgcolor=CARD_BG, border_radius=CARD_RADIUS,
                        padding=padding, expand=expand)


def page_column(controls, **kw):
    """Корневой Column вкладки: тянет карточки на всю ширину (STRETCH)."""
    return ft.Column(expand=True, spacing=GAP,
                     horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                     controls=controls, **kw)


def section_title(text, icon=None):
    row = []
    if icon:
        row.append(ft.Icon(icon, size=18, color=ACCENT))
    row.append(ft.Text(text, size=15, weight=ft.FontWeight.W_600))
    return ft.Row(row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)


# ──────────────────────────────────────────────────────────────
#  Вкладка 1 — CRM Воронка
# ──────────────────────────────────────────────────────────────
class ScoutTabView:
    _C = {"xs": 12, "sm": 6, "md": 4}

    def __init__(self, controller):
        self.controller = controller

        self.input_keyword = ft.TextField(label="Ключевое слово", value="QA Engineer",
                                           dense=True, expand=True,
                                           on_submit=controller.handle_search)
        self.combo_period = ft.Dropdown(label="Период", value="7", col=self._C, dense=True, options=[
            ft.DropdownOption(key="1",  text="За сутки"),
            ft.DropdownOption(key="3",  text="За 3 дня"),
            ft.DropdownOption(key="7",  text="За неделю"),
            ft.DropdownOption(key="30", text="За месяц"),
        ])
        self.combo_exp = ft.Dropdown(label="Опыт", value="between1And3", col=self._C, dense=True, options=[
            ft.DropdownOption(key="noExperience",  text="Без опыта"),
            ft.DropdownOption(key="between1And3",  text="1–3 года"),
            ft.DropdownOption(key="between3And6",  text="3–6 лет"),
            ft.DropdownOption(key="moreThan6",     text="Более 6 лет"),
        ])
        self.combo_schedule = ft.Dropdown(label="Формат", value="remote", col=self._C, dense=True, options=[
            ft.DropdownOption(key="remote",   text="Удалённая"),
            ft.DropdownOption(key="fullDay",  text="Полный день"),
            ft.DropdownOption(key="flexible", text="Гибкий"),
            ft.DropdownOption(key="shift",    text="Вахта"),
            ft.DropdownOption(key="",         text="Все форматы"),
        ])
        self.combo_area = ft.Dropdown(label="Регион", value="113", col=self._C, dense=True, options=[
            ft.DropdownOption(key="113", text="Вся Россия"),
            ft.DropdownOption(key="1",   text="Москва"),
            ft.DropdownOption(key="2",   text="Санкт-Петербург"),
        ])
        self.salary_exp_field = ft.TextField(
            label="Ожидаемая з/п, ₽", dense=True, col=self._C,
            hint_text="напр. 150000",
            input_filter=ft.NumbersOnlyInputFilter(),
            on_blur=controller.handle_salary_expectation_change,
            on_submit=controller.handle_salary_expectation_change,
        )
        self.combo_status_filter = ft.Dropdown(
            label="Этап воронки", value="all", col=self._C, dense=True,
            on_select=lambda e: self.controller.refresh_table_data(),
            options=[
                ft.DropdownOption(key="all",        text="Вся воронка"),
                ft.DropdownOption(key="discovered", text="Новые"),
                ft.DropdownOption(key="processed",  text="Письмо готово"),
                ft.DropdownOption(key="applied",    text="Отклик отправлен"),
                ft.DropdownOption(key="interview",  text="Собеседование"),
                ft.DropdownOption(key="offer",      text="Оффер!"),
                ft.DropdownOption(key="rejected",   text="Отказ"),
            ],
        )

        self.btn_search   = primary_btn("Найти",        controller.handle_search,           icon=ft.Icons.SEARCH)
        self.btn_export   = secondary_btn("Экспорт CSV", controller.handle_export,          icon=ft.Icons.DOWNLOAD)
        self.btn_resume   = secondary_btn("Резюме",      controller.handle_resume_upload,   icon=ft.Icons.UPLOAD_FILE)
        self.resume_label = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.btn_generate = primary_btn("ИИ-письмо",  controller.handle_generation,         icon=ft.Icons.AUTO_AWESOME)
        self.btn_analyze  = secondary_btn("Анализ ИИ", controller.handle_analyze,           icon=ft.Icons.INSIGHTS)
        self.btn_open_url = secondary_btn("hh.ru",     controller.open_vacancy_in_browser,  icon=ft.Icons.OPEN_IN_NEW)

        self.search_status   = ft.Text("", size=12, visible=False, color=ft.Colors.ON_SURFACE_VARIANT)
        self.search_progress = ft.ProgressBar(visible=False)
        self.funnel_counters = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)

        self.btn_toggle_filters = ft.IconButton(icon=ft.Icons.EXPAND_LESS, tooltip="Свернуть фильтры",
                                                on_click=controller.toggle_filters)
        self.filters_row = ft.Column(spacing=10, controls=[
            ft.Row([self.input_keyword, self.btn_search], spacing=8,
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.ResponsiveRow(run_spacing=10, spacing=10, controls=[
                self.combo_period, self.combo_exp, self.combo_schedule,
                self.combo_area, self.combo_status_filter, self.salary_exp_field,
            ]),
        ])

        self.table_empty_label = ft.Text(
            "Нажмите «Найти», чтобы загрузить вакансии с hh.ru",
            italic=True, color=ft.Colors.ON_SURFACE_VARIANT, size=13,
        )
        self.data_table = ft.DataTable(
            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            heading_text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
            column_spacing=24, divider_thickness=0.5,
            columns=[
                ft.DataColumn(ft.Text("Match")),
                ft.DataColumn(ft.Text("Компания")),
                ft.DataColumn(ft.Text("Вакансия")),
                ft.DataColumn(ft.Text("З/п")),
                ft.DataColumn(ft.Text("Статус")),
            ],
            rows=[],
        )

        # ── Панель деталей вакансии ───────────────────────────────
        self.detail_title = ft.Text("Вакансия не выбрана", size=18, weight=ft.FontWeight.BOLD)
        self.detail_meta  = ft.Text("Кликните строку в таблице слева, чтобы увидеть подробности.",
                                    color=ft.Colors.ON_SURFACE_VARIANT)
        self.detail_status = ft.Dropdown(
            label="Этап воронки", dense=True, visible=False,
            on_select=controller.handle_status_change,
            options=[
                ft.DropdownOption(key="discovered", text="Новая"),
                ft.DropdownOption(key="processed",  text="Письмо готово"),
                ft.DropdownOption(key="applied",    text="Отклик отправлен"),
                ft.DropdownOption(key="interview",  text="Собеседование"),
                ft.DropdownOption(key="offer",      text="Оффер!"),
                ft.DropdownOption(key="rejected",   text="Отказ"),
            ],
        )
        self.detail_skills = ft.Text("—", selectable=True)
        self.detail_description = ft.Text("", selectable=True, size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        self.detail_notes = ft.TextField(multiline=True, min_lines=2, dense=True,
                                         hint_text="Личные заметки по вакансии...",
                                         on_blur=controller.handle_notes_save)
        self.detail_analysis = ft.Markdown("", selectable=True,
                                           extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        self.detail_gaps = ft.Column(spacing=4)
        for b in (self.btn_generate, self.btn_analyze, self.btn_open_url):
            b.visible = False

    def build(self, wide: bool = True) -> ft.Control:
        filters = card(ft.Column(spacing=12, controls=[
            ft.Row(spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                section_title("Поиск вакансий на hh.ru", ft.Icons.TRAVEL_EXPLORE),
                self.btn_toggle_filters,
                ft.Container(expand=True),
                self.resume_label, self.btn_resume, self.btn_export,
            ]),
            self.filters_row,
            self.search_status,
            self.search_progress,
            self.funnel_counters,
        ]))

        table = card(ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[
            ft.Row(scroll=ft.ScrollMode.AUTO, controls=[self.data_table]),
            self.table_empty_label,
        ]), expand=True, padding=8)

        details = card(ft.Column(expand=True, spacing=10, controls=[
            self.detail_title,
            self.detail_meta,
            self.detail_status,
            ft.Row([self.btn_generate, self.btn_analyze, self.btn_open_url],
                   spacing=8, scroll=ft.ScrollMode.AUTO),
            ft.Divider(),
            ft.ListView(expand=True, spacing=10, controls=[
                section_title("Ключевые навыки", ft.Icons.BUILD_OUTLINED),
                self.detail_skills,
                section_title("Описание", ft.Icons.DESCRIPTION_OUTLINED),
                self.detail_description,
                section_title("Заметки", ft.Icons.EDIT_NOTE),
                self.detail_notes,
                section_title("Анализ ИИ", ft.Icons.INSIGHTS),
                self.detail_analysis,
                section_title("Чему подучиться", ft.Icons.SCHOOL),
                self.detail_gaps,
            ]),
        ]), expand=True)

        if wide:
            main = ft.Row(expand=True, spacing=GAP, controls=[
                ft.Column(expand=3, controls=[table]),
                ft.Column(expand=2, controls=[details]),
            ])
        else:
            main = ft.Column(expand=True, spacing=GAP, controls=[table, details])
        return page_column([filters, main])


# ──────────────────────────────────────────────────────────────
#  Вкладка 2 — Письма
# ──────────────────────────────────────────────────────────────
class LettersTabView:
    def __init__(self, controller):
        self.controller = controller
        self.vacancy_label = ft.Text(
            "Вакансия не выбрана — выберите её в CRM",
            size=13, color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
        )
        self.text_letter = ft.TextField(label="Сопроводительное письмо", multiline=True,
                                        min_lines=14, expand=True, border_color=ft.Colors.OUTLINE_VARIANT)
        self.text_recs = ft.TextField(label="Рекомендации к подготовке", multiline=True,
                                      min_lines=6, expand=True, read_only=True,
                                      border_color=ft.Colors.OUTLINE_VARIANT,
                                      hint_text="Появятся после генерации ИИ-письма")
        self.input_feedback = ft.TextField(label="Что исправить? Опишите правки для ИИ",
                                           expand=True, dense=True)
        self.btn_feedback   = secondary_btn("Исправить",  controller.handle_feedback, icon=ft.Icons.EDIT)
        self.btn_copy       = secondary_btn("Копировать", controller.copy_letter,     icon=ft.Icons.CONTENT_COPY)
        self.btn_auto_apply = primary_btn("Отправить автоотклик", controller.handle_auto_apply,
                                          icon=ft.Icons.SEND, bgcolor=ft.Colors.GREEN,
                                          color=ft.Colors.WHITE, expand=True)

    def build(self, wide: bool = True) -> ft.Control:
        editor = card(ft.Column(expand=True, spacing=8, controls=[
            ft.Row([section_title("Текст письма", ft.Icons.DESCRIPTION_OUTLINED),
                    ft.Container(expand=True), self.vacancy_label]),
            self.text_letter,
        ]), expand=True)
        recs = card(ft.Column(expand=True, spacing=8, controls=[
            section_title("Рекомендации ИИ", ft.Icons.LIGHTBULB_OUTLINE), self.text_recs,
        ]), expand=True)
        if wide:
            top = ft.Row(expand=True, spacing=GAP, controls=[
                ft.Column(expand=3, controls=[editor]),
                ft.Column(expand=2, controls=[recs]),
            ])
        else:
            top = ft.Column(expand=True, spacing=GAP, controls=[editor, recs])
        bottom = card(ft.Column(spacing=10, controls=[
            ft.Row(spacing=10, controls=[self.input_feedback, self.btn_feedback, self.btn_copy]),
            self.btn_auto_apply,
        ]))
        return page_column([top, bottom])


# ──────────────────────────────────────────────────────────────
#  Вкладка 3 — Mock-собеседование
# ──────────────────────────────────────────────────────────────
class InterviewTabView:
    def __init__(self, controller):
        self.controller = controller

        self.combo_format = ft.Dropdown(
            label="Формат", dense=True, value="tech", width=200,
            options=[
                ft.DropdownOption(key="tech",          text="Техническое"),
                ft.DropdownOption(key="hr",            text="HR-скрининг"),
                ft.DropdownOption(key="system_design", text="System Design"),
                ft.DropdownOption(key="behavioral",    text="Поведенческое (STAR)"),
            ],
        )
        self.chat_arena = ft.ListView(expand=True, spacing=10, auto_scroll=True, padding=4)
        self.input_chat = ft.TextField(label="Ваш ответ...", expand=True, dense=True,
                                       on_submit=controller.handle_send_chat)
        self.interview_vacancy_label = ft.Text(
            "Вакансия не выбрана", size=12,
            color=ft.Colors.ON_SURFACE_VARIANT, italic=True,
        )
        self.btn_send     = primary_btn("Отправить",  controller.handle_send_chat,    icon=ft.Icons.SEND)
        self.btn_start    = primary_btn("Начать",     controller.handle_start_mock,   icon=ft.Icons.PLAY_ARROW)
        self.btn_reset    = secondary_btn("Сбросить", controller.handle_reset_mock,   icon=ft.Icons.REFRESH)
        self.btn_evaluate = secondary_btn("Оценить сессию", controller.handle_evaluate_interview,
                                          icon=ft.Icons.ASSESSMENT)
        self.btn_evaluate.visible = False

        # Панель отчёта
        self.report_summary    = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        self.report_competencies = ft.Column(spacing=6)
        self.report_strengths  = ft.Text("", size=12)
        self.report_improvements = ft.Text("", size=12)
        self.report_recommendation = ft.Container(
            visible=False, border_radius=10, padding=ft.Padding(12, 8, 12, 8),
            content=ft.Text("", size=13, weight=ft.FontWeight.W_600),
        )
        self.report_placeholder = ft.Text(
            "Завершите сессию и нажмите «Оценить сессию»",
            italic=True, color=ft.Colors.ON_SURFACE_VARIANT, size=13,
        )
        self.report_panel = ft.Column(
            expand=True, scroll=ft.ScrollMode.AUTO, spacing=10,
            controls=[
                section_title("Отчёт по сессии", ft.Icons.ASSESSMENT),
                self.report_placeholder,
                self.report_summary,
                self.report_competencies,
                self.report_strengths,
                self.report_improvements,
                self.report_recommendation,
            ],
        )

    def build(self, wide: bool = True) -> ft.Control:
        controls_bar = card(ft.Column(spacing=8, controls=[
            ft.Row(
                spacing=10, wrap=False,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    section_title("Mock-собеседование с ИИ", ft.Icons.PSYCHOLOGY),
                    self.combo_format,
                    ft.Container(expand=True),
                    self.btn_start, self.btn_evaluate, self.btn_reset,
                ],
            ),
            self.interview_vacancy_label,
        ]), padding=12)
        chat  = card(self.chat_arena, expand=True, padding=12)
        input_bar = card(ft.Row(spacing=10, controls=[self.input_chat, self.btn_send]), padding=12)
        report = card(self.report_panel, expand=True, padding=14)

        if wide:
            mid = ft.Row(expand=True, spacing=GAP, controls=[
                ft.Column(expand=3, controls=[chat]),
                ft.Column(expand=2, controls=[report]),
            ])
        else:
            mid = ft.Column(expand=True, spacing=GAP, controls=[chat, report])
        return page_column([controls_bar, mid, input_bar])


# ──────────────────────────────────────────────────────────────
#  Вкладка 4 — Аналитика
# ──────────────────────────────────────────────────────────────
class AnalyticsTabView:
    def __init__(self, controller):
        self.controller = controller
        self.funnel_box = ft.Column(spacing=12)
        self.chart_image = ft.Image(src="data/chart.png", expand=True, fit=ft.BoxFit.CONTAIN, visible=False)
        self.placeholder = ft.Container(
            expand=True, alignment=ft.Alignment(0, 0),
            content=ft.Column(tight=True, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                ft.Icon(ft.Icons.INSERT_CHART_OUTLINED, size=64, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text("Постройте график, чтобы увидеть распределение зарплат",
                        color=ft.Colors.ON_SURFACE_VARIANT),
            ]),
        )
        self.btn_draw = primary_btn("Построить график зарплат",
                                    controller.draw_analytics_chart, icon=ft.Icons.BAR_CHART)

        # Хитмап навыков
        self.combo_heatmap_n = ft.Dropdown(
            label="Топ", value="20", dense=True, width=100,
            options=[
                ft.DropdownOption(key="10", text="10"),
                ft.DropdownOption(key="20", text="20"),
                ft.DropdownOption(key="30", text="30"),
            ],
        )
        self.btn_heatmap = primary_btn("Построить хитмап",
                                       controller.draw_skill_heatmap, icon=ft.Icons.LEADERBOARD)
        self.heatmap_placeholder = ft.Text(
            "Нажмите «Построить хитмап», чтобы увидеть топ навыков из ваших вакансий.",
            italic=True, color=ft.Colors.ON_SURFACE_VARIANT,
        )
        _legend = ft.Row(spacing=8, controls=[
            ft.Text("Грейды:", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Container(content=ft.Text("J — Junior",      size=10, color=ft.Colors.BLUE_300),
                         bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.BLUE_300),
                         border_radius=10, padding=ft.Padding(6, 2, 6, 2)),
            ft.Container(content=ft.Text("M — Middle",      size=10, color=ft.Colors.INDIGO_400),
                         bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.INDIGO_400),
                         border_radius=10, padding=ft.Padding(6, 2, 6, 2)),
            ft.Container(content=ft.Text("S — Senior/Lead", size=10, color=ft.Colors.PURPLE_400),
                         bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PURPLE_400),
                         border_radius=10, padding=ft.Padding(6, 2, 6, 2)),
        ])
        self.heatmap_box = ft.Column(scroll=ft.ScrollMode.AUTO, spacing=8,
                                     expand=True, controls=[_legend, self.heatmap_placeholder])

    def build(self, wide: bool = True) -> ft.Control:
        funnel = card(ft.Column(spacing=10, controls=[
            section_title("Воронка поиска работы", ft.Icons.FILTER_ALT), self.funnel_box,
        ]))
        chart = card(ft.Column(expand=True, spacing=10, controls=[
            ft.Row(controls=[
                section_title("Зарплаты на рынке", ft.Icons.QUERY_STATS),
                ft.Container(expand=True), self.btn_draw,
            ]),
            ft.Container(expand=True, content=ft.Stack(expand=True,
                                                        controls=[self.placeholder, self.chart_image])),
        ]), expand=True)
        heatmap = card(ft.Column(expand=True, spacing=10, controls=[
            ft.Row(controls=[
                section_title("Топ навыков рынка", ft.Icons.LEADERBOARD),
                ft.Container(expand=True),
                self.combo_heatmap_n, self.btn_heatmap,
            ]),
            self.heatmap_box,
        ]), expand=True)
        if wide:
            bottom = ft.Row(expand=True, spacing=GAP, controls=[
                ft.Column(expand=1, controls=[chart]),
                ft.Column(expand=1, controls=[heatmap]),
            ])
        else:
            bottom = ft.Column(expand=True, spacing=GAP, controls=[chart, heatmap])
        return page_column([funnel, bottom])


# ──────────────────────────────────────────────────────────────
#  Вкладка 5 — Учебник QA
# ──────────────────────────────────────────────────────────────
class HandbookTabView:
    def __init__(self, controller):
        self.controller = controller
        self.search_field = ft.TextField(hint_text="Поиск по темам...", dense=True,
                                         prefix_icon=ft.Icons.SEARCH,
                                         on_change=controller.handle_handbook_search)
        self.btn_mode_sections = ft.TextButton(content=ft.Text("Разделы"), icon=ft.Icons.MENU_BOOK,
                                               on_click=lambda e: controller.set_handbook_mode("sections"))
        self.btn_mode_fav = ft.TextButton(content=ft.Text("Избранное"), icon=ft.Icons.STAR,
                                          on_click=lambda e: controller.set_handbook_mode("favorites"))
        self.btn_mode_plan = ft.TextButton(content=ft.Text("План"), icon=ft.Icons.CHECKLIST,
                                           on_click=lambda e: controller.set_handbook_mode("plan"))
        self.btn_mode_cards = ft.TextButton(content=ft.Text("Карточки"), icon=ft.Icons.STYLE,
                                            on_click=lambda e: controller.set_handbook_mode("cards"))

        self.progress_label = ft.Text("Прогресс 0% (0 из 0)", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
        self.progress_bar = ft.ProgressBar(value=0, color=ft.Colors.GREEN_500)

        self.tree_handbook = ft.ListView(expand=True, spacing=2, padding=4)
        self.text_handbook = ft.Markdown(value="Выберите вопрос в списке слева, чтобы увидеть ответ.",
                                         selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        self.topic_title = ft.Text("", weight=ft.FontWeight.BOLD, size=15)
        self.topic_badge = ft.Text("", size=11, color=ft.Colors.AMBER_400)
        self.btn_studied = ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, visible=False,
                                         tooltip="Отметить изученным",
                                         on_click=controller.handle_handbook_studied)
        self.btn_fav = ft.IconButton(icon=ft.Icons.STAR_BORDER, visible=False, tooltip="В избранное",
                                     on_click=controller.handle_handbook_favorite)
        self.btn_edit = secondary_btn("Редактировать", controller.handle_handbook_edit, icon=ft.Icons.EDIT)
        self.btn_edit.visible = False
        self.editor = ft.TextField(multiline=True, expand=True, min_lines=10,
                                   border_color=ft.Colors.OUTLINE_VARIANT)
        self.instr_field = ft.TextField(
            hint_text="Что поправить? напр. «добавь пример кода и кратко про плюсы/минусы»",
            dense=True, expand=True)
        self.btn_ai_fix = secondary_btn("Поправить ИИ", controller.handle_handbook_ai_fix,
                                        icon=ft.Icons.AUTO_AWESOME)
        self.btn_save   = primary_btn("Сохранить", controller.handle_handbook_save, icon=ft.Icons.SAVE)
        self.btn_cancel = secondary_btn("Отмена", controller.handle_handbook_cancel, icon=ft.Icons.CLOSE)
        self.view_box = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[self.text_handbook])
        self.edit_box = ft.Column(expand=True, spacing=8, visible=False, controls=[
            ft.Text("Текст ответа (обычный текст / Markdown — заголовки ###, списки -, код в ```):",
                    size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            self.editor,
            ft.Row([self.instr_field, self.btn_ai_fix], spacing=8),
            ft.Row([self.btn_save, self.btn_cancel], spacing=8),
        ])

        # Флеш-карточки
        self.cards_scope = ft.Dropdown(label="Что повторяем", value="all", dense=True, options=[
            ft.DropdownOption(key="all",       text="Все темы"),
            ft.DropdownOption(key="favorites", text="Только избранное"),
            ft.DropdownOption(key="unstudied", text="Ещё не изученные"),
        ])
        self.btn_cards_start = primary_btn("Начать", controller.handle_cards_start, icon=ft.Icons.PLAY_ARROW)
        self.cards_controls = ft.Column(visible=False, spacing=10, controls=[
            ft.Text("Режим повторения карточками", weight=ft.FontWeight.W_600),
            self.cards_scope, self.btn_cards_start,
        ])
        self.card_progress = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.card_question = ft.Text("Выберите область и нажмите «Начать».", size=18, weight=ft.FontWeight.BOLD)
        self.btn_reveal = primary_btn("Показать ответ", controller.handle_cards_reveal, icon=ft.Icons.VISIBILITY)
        self.btn_reveal.visible = False
        self.card_answer = ft.Markdown("", selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        self.card_answer_box = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, visible=False,
                                         controls=[self.card_answer])
        self.btn_know = primary_btn("Знаю", controller.handle_cards_know, icon=ft.Icons.CHECK,
                                    bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
        self.btn_repeat = secondary_btn("Повторить", controller.handle_cards_repeat, icon=ft.Icons.REFRESH)
        self.card_actions = ft.Row([self.btn_know, self.btn_repeat], spacing=8, visible=False)
        self.card_box = ft.Column(expand=True, spacing=12, visible=False, controls=[
            self.card_progress,
            ft.Container(content=self.card_question, padding=ft.Padding(0, 20, 0, 8)),
            self.btn_reveal, self.card_answer_box, self.card_actions,
        ])

        # Панель темы (персистентна)
        self.topic_pane = ft.Column(expand=True, spacing=8, controls=[
            ft.Row([self.topic_title, self.topic_badge, ft.Container(expand=True),
                    self.btn_studied, self.btn_fav, self.btn_edit],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1),
            self.view_box, self.edit_box,
        ])

    def build(self, wide: bool = True) -> ft.Control:
        left = card(ft.Column(expand=True, spacing=8, controls=[
            ft.Row([self.btn_mode_sections, self.btn_mode_fav, self.btn_mode_plan, self.btn_mode_cards],
                   scroll=ft.ScrollMode.AUTO, spacing=2),
            self.progress_label, self.progress_bar, self.search_field,
            self.tree_handbook, self.cards_controls,
        ]), expand=True, padding=10)
        right = card(ft.Column(expand=True, controls=[self.topic_pane, self.card_box]), expand=True)
        if wide:
            return ft.Row(expand=True, spacing=GAP, controls=[
                ft.Container(width=340, content=left), right,
            ])
        return ft.Column(expand=True, spacing=GAP, controls=[
            ft.Container(height=240, content=left), right,
        ])


# ──────────────────────────────────────────────────────────────
#  Вкладка 6 — Логи
# ──────────────────────────────────────────────────────────────
class LogsTabView:
    def __init__(self, controller):
        self.controller = controller
        self.logs_text = ft.TextField(value="", multiline=True, read_only=True, expand=True,
                                      min_lines=20, text_size=12,
                                      text_style=ft.TextStyle(font_family="Consolas"),
                                      border_color=ft.Colors.OUTLINE_VARIANT)
        self.btn_clear = secondary_btn("Очистить", controller.handle_clear_logs,
                                       icon=ft.Icons.DELETE_SWEEP)

    def build(self, wide: bool = True) -> ft.Control:
        return page_column([card(ft.Column(expand=True, spacing=8, controls=[
            ft.Row([section_title("Журнал событий", ft.Icons.TERMINAL),
                    ft.Container(expand=True), self.btn_clear]),
            self.logs_text,
        ]), expand=True)])


# ──────────────────────────────────────────────────────────────
#  Главное окно
# ──────────────────────────────────────────────────────────────
class MainView:
    def __init__(self, controller):
        self.controller = controller
        self._page: ft.Page | None = None

        self.scout_tab     = ScoutTabView(controller)
        self.letters_tab   = LettersTabView(controller)
        self.interview_tab = InterviewTabView(controller)
        self.analytics_tab = AnalyticsTabView(controller)
        self.handbook_tab  = HandbookTabView(controller)
        self.logs_tab      = LogsTabView(controller)

        self._tab_views = [
            self.scout_tab, self.letters_tab, self.interview_tab,
            self.analytics_tab, self.handbook_tab, self.logs_tab,
        ]
        self._index = 0
        self._wide = True

        self.body = ft.Container(content=self._tab_views[0].build(self._wide),
                                 expand=True, padding=ft.Padding(16, 12, 16, 8))

        self.nav_bar = ft.NavigationBar(
            selected_index=0, on_change=self._on_nav_change,
            height=58, label_behavior=ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.SEARCH,           label="CRM"),
                ft.NavigationBarDestination(icon=ft.Icons.MAIL_OUTLINE,      label="Письма"),
                ft.NavigationBarDestination(icon=ft.Icons.RECORD_VOICE_OVER, label="Интервью"),
                ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART,         label="Аналитика"),
                ft.NavigationBarDestination(icon=ft.Icons.BOOK_OUTLINED,     label="Учебник"),
                ft.NavigationBarDestination(icon=ft.Icons.TERMINAL,          label="Логи"),
            ],
        )

    def _header(self) -> ft.Control:
        return ft.Container(
            padding=ft.Padding(20, 14, 20, 14),
            content=ft.Row(spacing=14, vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                ft.Container(width=44, height=44, border_radius=12, bgcolor=ft.Colors.INDIGO,
                             alignment=ft.Alignment(0, 0),
                             content=ft.Icon(ft.Icons.WORK, color=ft.Colors.WHITE, size=24)),
                ft.Column(spacing=0, controls=[
                    ft.Text("QA Smart Assistant Pro", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text("Поиск вакансий · письма · собеседования", size=12,
                            color=ft.Colors.ON_SURFACE_VARIANT),
                ]),
            ]),
        )

    def _render_active(self):
        self.body.content = self._tab_views[self._index].build(self._wide)
        if self._page:
            self._page.update()

    def switch_to_tab(self, index: int):
        self._index = index
        self.nav_bar.selected_index = index
        self._render_active()

    def _on_nav_change(self, e):
        self._index = e.control.selected_index
        self._render_active()

    def _on_resize(self, e):
        new_wide = (self._page.width or BREAKPOINT + 1) >= BREAKPOINT
        if new_wide != self._wide:
            self._wide = new_wide
            self._render_active()

    def setup_page(self, page: ft.Page):
        self._page = page
        self._wide = (page.width or BREAKPOINT + 1) >= BREAKPOINT
        page.on_resize = self._on_resize
        page.navigation_bar = self.nav_bar
        page.controls = [
            ft.Column(expand=True, spacing=0, controls=[
                self._header(),
                ft.Divider(height=1, thickness=1),
                self.body,
            ])
        ]
        self._render_active()
        page.update()
