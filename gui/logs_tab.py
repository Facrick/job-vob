import flet as ft

from gui.components import card, page_column, secondary_btn, section_title


# ──────────────────────────────────────────────────────────────
#  Вкладка 6 — Логи
# ──────────────────────────────────────────────────────────────
class LogsTabView:
    def __init__(self, controller):
        self.controller = controller
        self.logs_text = ft.TextField(
            value="",
            multiline=True,
            read_only=True,
            expand=True,
            min_lines=20,
            text_size=12,
            text_style=ft.TextStyle(font_family="Consolas"),
            border_color=ft.Colors.OUTLINE_VARIANT,
        )
        self.btn_clear = secondary_btn(
            "Очистить", controller.handle_clear_logs, icon=ft.Icons.DELETE_SWEEP
        )

    def build(self, wide: bool = True) -> ft.Control:
        return page_column(
            [
                card(
                    ft.Column(
                        expand=True,
                        spacing=8,
                        controls=[
                            ft.Row(
                                [
                                    section_title("Журнал событий", ft.Icons.TERMINAL),
                                    ft.Container(expand=True),
                                    self.btn_clear,
                                ]
                            ),
                            self.logs_text,
                        ],
                    ),
                    expand=True,
                )
            ]
        )
