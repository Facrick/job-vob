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
#  Вкладка 3 — Mock-собеседование
# ──────────────────────────────────────────────────────────────
class InterviewTabView:
    def __init__(self, controller):
        self.controller = controller

        self.combo_format = ft.Dropdown(
            label="Формат",
            dense=True,
            value="tech",
            width=200,
            options=[
                ft.DropdownOption(key="tech", text="Техническое"),
                ft.DropdownOption(key="hr", text="HR-скрининг"),
                ft.DropdownOption(key="system_design", text="System Design"),
                ft.DropdownOption(key="behavioral", text="Поведенческое (STAR)"),
            ],
        )
        self.chat_arena = ft.ListView(
            expand=True, spacing=10, auto_scroll=True, padding=4
        )
        self.input_chat = ft.TextField(
            label="Ваш ответ...",
            expand=True,
            dense=True,
            on_submit=controller.handle_send_chat,
        )
        self.interview_vacancy_label = ft.Text(
            "Вакансия не выбрана",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
        )
        self.btn_send = primary_btn(
            "Отправить", controller.handle_send_chat, icon=ft.Icons.SEND
        )
        self.btn_start = primary_btn(
            "Начать", controller.handle_start_mock, icon=ft.Icons.PLAY_ARROW
        )
        self.btn_reset = secondary_btn(
            "Сбросить", controller.handle_reset_mock, icon=ft.Icons.REFRESH
        )
        self.btn_evaluate = secondary_btn(
            "Оценить сессию",
            controller.handle_evaluate_interview,
            icon=ft.Icons.ASSESSMENT,
        )
        self.btn_evaluate.visible = False

        # Панель отчёта
        self.report_summary = ft.Text("", size=13, color=ft.Colors.ON_SURFACE_VARIANT)
        self.report_competencies = ft.Column(spacing=6)
        self.report_strengths = ft.Text("", size=12)
        self.report_improvements = ft.Text("", size=12)
        self.report_recommendation = ft.Container(
            visible=False,
            border_radius=10,
            padding=ft.Padding(12, 8, 12, 8),
            content=ft.Text("", size=13, weight=ft.FontWeight.W_600),
        )
        self.report_placeholder = ft.Text(
            "Завершите сессию и нажмите «Оценить сессию»",
            italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
            size=13,
        )
        self.report_panel = ft.Column(
            expand=True,
            scroll=ft.ScrollMode.AUTO,
            spacing=10,
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
        controls_bar = card(
            ft.Column(
                spacing=8,
                controls=[
                    ft.Row(
                        spacing=10,
                        wrap=False,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        controls=[
                            section_title(
                                "Mock-собеседование с ИИ", ft.Icons.PSYCHOLOGY
                            ),
                            self.combo_format,
                            ft.Container(expand=True),
                            self.btn_start,
                            self.btn_evaluate,
                            self.btn_reset,
                        ],
                    ),
                    self.interview_vacancy_label,
                ],
            ),
            padding=12,
        )
        chat = card(self.chat_arena, expand=True, padding=12)
        input_bar = card(
            ft.Row(spacing=10, controls=[self.input_chat, self.btn_send]), padding=12
        )
        report = card(self.report_panel, expand=True, padding=14)

        if wide:
            mid = ft.Row(
                expand=True,
                spacing=GAP,
                controls=[
                    ft.Column(expand=3, controls=[chat]),
                    ft.Column(expand=2, controls=[report]),
                ],
            )
        else:
            mid = ft.Column(expand=True, spacing=GAP, controls=[chat, report])
        return page_column([controls_bar, mid, input_bar])
