import flet as ft

from gui.components import (
    GAP,
    card,
    page_column,
    primary_btn,
    secondary_btn,
    section_title,
)


# ──────────────────────────────────────────────────────────────
#  Вкладка 1 — CRM Воронка
# ──────────────────────────────────────────────────────────────
class ScoutTabView:
    _C = {"xs": 12, "sm": 6, "md": 4}

    def __init__(self, controller):
        self.controller = controller

        self.input_keyword = ft.TextField(
            label="Ключевое слово",
            value="QA Engineer",
            dense=True,
            expand=True,
            on_submit=controller.handle_search,
        )
        self.combo_period = ft.Dropdown(
            label="Период",
            value="7",
            col=self._C,
            dense=True,
            options=[
                ft.DropdownOption(key="1", text="За сутки"),
                ft.DropdownOption(key="3", text="За 3 дня"),
                ft.DropdownOption(key="7", text="За неделю"),
                ft.DropdownOption(key="30", text="За месяц"),
            ],
        )
        self.combo_exp = ft.Dropdown(
            label="Опыт",
            value="between1And3",
            col=self._C,
            dense=True,
            options=[
                ft.DropdownOption(key="noExperience", text="Без опыта"),
                ft.DropdownOption(key="between1And3", text="1–3 года"),
                ft.DropdownOption(key="between3And6", text="3–6 лет"),
                ft.DropdownOption(key="moreThan6", text="Более 6 лет"),
            ],
        )
        self.combo_schedule = ft.Dropdown(
            label="Формат",
            value="remote",
            col=self._C,
            dense=True,
            options=[
                ft.DropdownOption(key="remote", text="Удалённая"),
                ft.DropdownOption(key="fullDay", text="Полный день"),
                ft.DropdownOption(key="flexible", text="Гибкий"),
                ft.DropdownOption(key="shift", text="Вахта"),
                ft.DropdownOption(key="", text="Все форматы"),
            ],
        )
        self.combo_area = ft.Dropdown(
            label="Регион",
            value="113",
            col=self._C,
            dense=True,
            options=[
                ft.DropdownOption(key="113", text="Вся Россия"),
                ft.DropdownOption(key="1", text="Москва"),
                ft.DropdownOption(key="2", text="Санкт-Петербург"),
            ],
        )
        self.salary_exp_field = ft.TextField(
            label="Ожидаемая з/п, ₽",
            dense=True,
            col=self._C,
            hint_text="напр. 150000",
            input_filter=ft.NumbersOnlyInputFilter(),
            on_blur=controller.handle_salary_expectation_change,
            on_submit=controller.handle_salary_expectation_change,
        )
        self.combo_status_filter = ft.Dropdown(
            label="Этап воронки",
            value="all",
            col=self._C,
            dense=True,
            on_select=lambda e: self.controller.refresh_table_data(),
            options=[
                ft.DropdownOption(key="all", text="Вся воронка"),
                ft.DropdownOption(key="discovered", text="Новые"),
                ft.DropdownOption(key="processed", text="Письмо готово"),
                ft.DropdownOption(key="applied", text="Отклик отправлен"),
                ft.DropdownOption(key="interview", text="Собеседование"),
                ft.DropdownOption(key="offer", text="Оффер!"),
                ft.DropdownOption(key="rejected", text="Отказ"),
            ],
        )

        self.btn_search = primary_btn(
            "Найти", controller.handle_search, icon=ft.Icons.SEARCH
        )
        self.btn_export = secondary_btn(
            "Экспорт CSV", controller.handle_export, icon=ft.Icons.DOWNLOAD
        )
        self.btn_resume = secondary_btn(
            "Резюме", controller.handle_resume_upload, icon=ft.Icons.UPLOAD_FILE
        )
        self.resume_label = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.btn_generate = primary_btn(
            "ИИ-письмо", controller.handle_generation, icon=ft.Icons.AUTO_AWESOME
        )
        self.btn_analyze = secondary_btn(
            "Анализ ИИ", controller.handle_analyze, icon=ft.Icons.INSIGHTS
        )
        self.btn_open_url = secondary_btn(
            "hh.ru", controller.open_vacancy_in_browser, icon=ft.Icons.OPEN_IN_NEW
        )

        self.search_status = ft.Text(
            "", size=12, visible=False, color=ft.Colors.ON_SURFACE_VARIANT
        )
        self.search_progress = ft.ProgressBar(visible=False)
        self.funnel_counters = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=8)

        self.btn_toggle_filters = ft.IconButton(
            icon=ft.Icons.EXPAND_LESS,
            tooltip="Свернуть фильтры",
            on_click=controller.toggle_filters,
        )
        self.filters_row = ft.Column(
            spacing=10,
            controls=[
                ft.Row(
                    [self.input_keyword, self.btn_search],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.ResponsiveRow(
                    run_spacing=10,
                    spacing=10,
                    controls=[
                        self.combo_period,
                        self.combo_exp,
                        self.combo_schedule,
                        self.combo_area,
                        self.combo_status_filter,
                        self.salary_exp_field,
                    ],
                ),
            ],
        )

        self.table_empty_label = ft.Text(
            "Нажмите «Найти», чтобы загрузить вакансии с hh.ru",
            italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
            size=13,
        )
        self.data_table = ft.DataTable(
            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            heading_text_style=ft.TextStyle(weight=ft.FontWeight.BOLD),
            column_spacing=24,
            divider_thickness=0.5,
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
        self.detail_title = ft.Text(
            "Вакансия не выбрана", size=18, weight=ft.FontWeight.BOLD
        )
        self.detail_meta = ft.Text(
            "Кликните строку в таблице слева, чтобы увидеть подробности.",
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        self.detail_status = ft.Dropdown(
            label="Этап воронки",
            dense=True,
            visible=False,
            on_select=controller.handle_status_change,
            options=[
                ft.DropdownOption(key="discovered", text="Новая"),
                ft.DropdownOption(key="processed", text="Письмо готово"),
                ft.DropdownOption(key="applied", text="Отклик отправлен"),
                ft.DropdownOption(key="interview", text="Собеседование"),
                ft.DropdownOption(key="offer", text="Оффер!"),
                ft.DropdownOption(key="rejected", text="Отказ"),
            ],
        )
        self.detail_skills = ft.Text("—", selectable=True)
        self.detail_description = ft.Text(
            "", selectable=True, size=13, color=ft.Colors.ON_SURFACE_VARIANT
        )
        self.detail_notes = ft.TextField(
            multiline=True,
            min_lines=2,
            dense=True,
            hint_text="Личные заметки по вакансии...",
            on_blur=controller.handle_notes_save,
        )
        self.detail_analysis = ft.Markdown(
            "", selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB
        )
        self.detail_gaps = ft.Column(spacing=4)
        for b in (self.btn_generate, self.btn_analyze, self.btn_open_url):
            b.visible = False

    def build(self, wide: bool = True) -> ft.Control:
        filters = card(
            ft.Column(
                spacing=12,
                controls=[
                    ft.Row(
                        spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            section_title(
                                "Поиск вакансий на hh.ru", ft.Icons.TRAVEL_EXPLORE
                            ),
                            self.btn_toggle_filters,
                            ft.Container(expand=True),
                            self.resume_label,
                            self.btn_resume,
                            self.btn_export,
                        ],
                    ),
                    self.filters_row,
                    self.search_status,
                    self.search_progress,
                    self.funnel_counters,
                ],
            )
        )

        table = card(
            ft.Column(
                expand=True,
                scroll=ft.ScrollMode.AUTO,
                controls=[
                    ft.Row(scroll=ft.ScrollMode.AUTO, controls=[self.data_table]),
                    self.table_empty_label,
                ],
            ),
            expand=True,
            padding=8,
        )

        details = card(
            ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    self.detail_title,
                    self.detail_meta,
                    self.detail_status,
                    ft.Row(
                        [self.btn_generate, self.btn_analyze, self.btn_open_url],
                        spacing=8,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    ft.Divider(),
                    ft.ListView(
                        expand=True,
                        spacing=10,
                        controls=[
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
                        ],
                    ),
                ],
            ),
            expand=True,
        )

        if wide:
            main = ft.Row(
                expand=True,
                spacing=GAP,
                controls=[
                    ft.Column(expand=3, controls=[table]),
                    ft.Column(expand=2, controls=[details]),
                ],
            )
        else:
            main = ft.Column(expand=True, spacing=GAP, controls=[table, details])
        return page_column([filters, main])
