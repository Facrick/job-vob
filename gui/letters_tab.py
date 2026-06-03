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
#  Вкладка 2 — Письма
# ──────────────────────────────────────────────────────────────
class LettersTabView:
    def __init__(self, controller):
        self.controller = controller
        self.vacancy_label = ft.Text(
            "Вакансия не выбрана — выберите её в CRM",
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            italic=True,
        )
        self.text_letter = ft.TextField(
            hint_text="Сопроводительное письмо появится здесь после генерации…",
            multiline=True,
            min_lines=14,
            expand=True,
            border_color=ft.Colors.OUTLINE_VARIANT,
        )
        self.text_recs = ft.TextField(
            hint_text="Рекомендации ИИ появятся здесь после генерации…",
            multiline=True,
            min_lines=6,
            expand=True,
            read_only=True,
            border_color=ft.Colors.OUTLINE_VARIANT,
        )
        self.input_feedback = ft.TextField(
            label="Что исправить? Опишите правки для ИИ", expand=True, dense=True
        )
        self.btn_feedback = secondary_btn(
            "Исправить", controller.handle_feedback, icon=ft.Icons.EDIT
        )
        self.btn_copy = secondary_btn(
            "Копировать", controller.copy_letter, icon=ft.Icons.CONTENT_COPY
        )
        self.btn_auto_apply = primary_btn(
            "Отправить автоотклик",
            controller.handle_auto_apply,
            icon=ft.Icons.SEND,
            bgcolor=ft.Colors.GREEN,
            color=ft.Colors.WHITE,
            expand=True,
        )

    def build(self, wide: bool = True) -> ft.Control:
        editor = card(
            ft.Column(
                expand=True,
                spacing=8,
                controls=[
                    ft.Row(
                        [
                            section_title(
                                "Текст письма", ft.Icons.DESCRIPTION_OUTLINED
                            ),
                            ft.Container(expand=True),
                            self.vacancy_label,
                        ]
                    ),
                    self.text_letter,
                ],
            ),
            expand=True,
        )
        recs = card(
            ft.Column(
                expand=True,
                spacing=8,
                controls=[
                    section_title("Рекомендации ИИ", ft.Icons.LIGHTBULB_OUTLINE),
                    self.text_recs,
                ],
            ),
            expand=True,
        )
        if wide:
            top = ft.Row(
                expand=True,
                spacing=GAP,
                controls=[
                    ft.Column(expand=3, controls=[editor]),
                    ft.Column(expand=2, controls=[recs]),
                ],
            )
        else:
            top = ft.Column(expand=True, spacing=GAP, controls=[editor, recs])
        bottom = card(
            ft.Column(
                spacing=10,
                controls=[
                    ft.Row(
                        spacing=10,
                        controls=[
                            self.input_feedback,
                            self.btn_feedback,
                            self.btn_copy,
                        ],
                    ),
                    self.btn_auto_apply,
                ],
            )
        )
        return page_column([top, bottom])
