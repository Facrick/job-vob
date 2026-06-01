import flet as ft

@ft.control("ScoutTabView")
class ScoutTabView(ft.BaseControl):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        # Виджеты создаём в __init__, чтобы контроллер мог обращаться к ним
        # до первого вызова build() (например, в bind_flet_view → refresh_table_data)
        self.input_keyword = ft.TextField(label="Поиск", value="QA Engineer", expand=True)
        self.combo_period = ft.Dropdown(
            label="Период",
            options=[
                ft.dropdown.Option(key="1", text="За сутки"),
                ft.dropdown.Option(key="3", text="За 3 дня"),
                ft.dropdown.Option(key="7", text="За неделю"),
                ft.dropdown.Option(key="30", text="За месяц"),
            ],
            value="1",
        )
        self.combo_exp = ft.Dropdown(
            label="Опыт",
            options=[
                ft.dropdown.Option(key="between1And3", text="1–3 года"),
                ft.dropdown.Option(key="noExperience", text="Без опыта"),
                ft.dropdown.Option(key="between3And6", text="3–6 лет"),
            ],
            value="between1And3",
        )
        self.combo_schedule = ft.Dropdown(
            label="Формат",
            options=[
                ft.dropdown.Option(key="remote", text="Удаленная работа"),
                ft.dropdown.Option(key="", text="Все форматы"),
                ft.dropdown.Option(key="fullDay", text="Полный день"),
            ],
            value="remote",
        )
        self.combo_area = ft.Dropdown(
            label="Регион",
            options=[
                ft.dropdown.Option(key="113", text="Вся Россия"),
                ft.dropdown.Option(key="1", text="Москва"),
                ft.dropdown.Option(key="2", text="Санкт-Петербург"),
            ],
            value="113",
        )
        self.combo_status_filter = ft.Dropdown(
            label="Фильтр CRM",
            options=[
                ft.dropdown.Option(key="all", text="Вся воронка"),
                ft.dropdown.Option(key="discovered", text="1. Новые"),
                ft.dropdown.Option(key="processed", text="2. Письмо готово"),
                ft.dropdown.Option(key="applied", text="3. Отклик отправлен"),
                ft.dropdown.Option(key="interview", text="4. Собеседование"),
                ft.dropdown.Option(key="offer", text="5. Оффер!"),
                ft.dropdown.Option(key="rejected", text="6. Отказ"),
            ],
            value="all",
            on_select=lambda e: self.controller.refresh_table_data(),
        )
        self.btn_search = ft.ElevatedButton(text="🔍 Найти", on_click=self.controller.handle_search)
        self.data_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Company")),
                ft.DataColumn(ft.Text("Vacancy")),
                ft.DataColumn(ft.Text("ID")),
                ft.DataColumn(ft.Text("Этап воронки")),
                ft.DataColumn(ft.Text("Ссылка")),
            ],
            rows=[],
        )

    def build(self):
        filter_row = ft.Row(
            controls=[
                self.input_keyword,
                self.combo_period,
                self.combo_exp,
                self.combo_schedule,
                self.combo_area,
                self.combo_status_filter,
                self.btn_search,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
        return ft.Column(controls=[filter_row, self.data_table])

@ft.control("LettersTabView")
class LettersTabView(ft.BaseControl):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.text_letter = ft.TextField(label="Сопроводительное письмо", multiline=True, min_lines=15)
        self.text_recs = ft.TextField(label="Рекомендации для подготовки", multiline=True, min_lines=5)
        self.input_feedback = ft.TextField(label="Что исправить в письме?")
        self.btn_apply_feedback = ft.ElevatedButton(
            text="🛠️ Применить правки", on_click=self.controller.handle_feedback
        )
        self.btn_auto_apply = ft.ElevatedButton(
            text="🚀 Отправить автоотклик",
            on_click=self.controller.handle_auto_apply,
            bgcolor=ft.Colors.GREEN,
            color=ft.Colors.WHITE,
        )

    def build(self):
        left_panel = ft.Column(
            controls=[
                self.text_letter,
                ft.Row(controls=[self.input_feedback, self.btn_apply_feedback]),
                self.btn_auto_apply,
            ],
            expand=2,
        )
        right_panel = ft.Column(controls=[self.text_recs], expand=1)
        return ft.Row(controls=[left_panel, right_panel])

@ft.control("InterviewTabView")
class InterviewTabView(ft.BaseControl):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.chat_arena = ft.ListView(expand=True, spacing=10, auto_scroll=True)
        self.input_chat = ft.TextField(label="Ваш ответ...", on_submit=self.controller.handle_send_chat)
        self.btn_send_chat = ft.ElevatedButton(text="Отправить", on_click=self.controller.handle_send_chat)
        self.btn_start_mock = ft.ElevatedButton(
            text="🚀 Начать собеседование", on_click=self.controller.handle_start_mock
        )
        self.btn_reset_mock = ft.ElevatedButton(
            text="🔄 Сбросить", on_click=self.controller.handle_reset_mock
        )

    def build(self):
        return ft.Column(
            controls=[
                self.chat_arena,
                ft.Row(controls=[self.input_chat, self.btn_send_chat]),
                ft.Row(controls=[self.btn_start_mock, self.btn_reset_mock]),
            ]
        )

@ft.control("AnalyticsTabView")
class AnalyticsTabView(ft.BaseControl):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.chart_image = ft.Image(src="data/chart.png", expand=True)
        self.btn_draw_chart = ft.ElevatedButton(
            text="📈 Рассчитать и обновить график",
            on_click=self.controller.draw_analytics_chart,
        )

    def build(self):
        return ft.Column(controls=[self.btn_draw_chart, self.chart_image])

@ft.control("HandbookTabView")
class HandbookTabView(ft.BaseControl):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.tree_handbook = ft.ListView(expand=True, spacing=5)
        self.text_handbook = ft.Markdown(expand=True)

    def build(self):
        return ft.Row(
            controls=[self.tree_handbook, self.text_handbook],
            expand=True,
        )

@ft.control("LogsTabView")
class LogsTabView(ft.BaseControl):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.logs_text = ft.Text("", selectable=True, expand=True) # Инициализируем здесь

    def build(self):
        return ft.ListView(controls=[self.logs_text], expand=True, auto_scroll=True)


@ft.control("MainView")
class MainView(ft.BaseControl):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.scout_tab = ScoutTabView(self.controller)
        self.letters_tab = LettersTabView(self.controller)
        self.interview_tab = InterviewTabView(self.controller)
        self.analytics_tab = AnalyticsTabView(self.controller)
        self.handbook_tab = HandbookTabView(self.controller)
        self.logs_tab = LogsTabView(self.controller)

    def build(self):
        self.tabs = ft.Tabs(
            selected_index=0,
            animation_duration=300,
            tabs=[
                ft.Tab(text="🔍 CRM Воронка", content=self.scout_tab),
                ft.Tab(text="✉️ Письма", content=self.letters_tab),
                ft.Tab(text="🤖 Собеседования", content=self.interview_tab),
                ft.Tab(text="📊 Графики з/п", content=self.analytics_tab),
                ft.Tab(text="📚 Учебник QA", content=self.handbook_tab),
                ft.Tab(text="📋 Логи", content=self.logs_tab),
            ],
            expand=1,
        )
        
        return self.tabs
