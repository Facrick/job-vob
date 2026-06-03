import flet as ft

from gui.components import GAP, card, page_column, primary_btn, section_title


# ──────────────────────────────────────────────────────────────
#  Вкладка 4 — Аналитика
# ──────────────────────────────────────────────────────────────
class AnalyticsTabView:
    def __init__(self, controller):
        self.controller = controller
        self.funnel_box = ft.Column(spacing=12)
        self.salary_stats_row = ft.Row(spacing=12, wrap=True)
        self.salary_chart_col = ft.Column(spacing=6, scroll=ft.ScrollMode.AUTO, expand=True)
        self.salary_chart_placeholder = ft.Text(
            "Нажмите «Обновить» чтобы построить график",
            italic=True, color=ft.Colors.ON_SURFACE_VARIANT
        )
        self.btn_draw = primary_btn(
            "Построить график зарплат",
            controller.draw_analytics_chart,
            icon=ft.Icons.BAR_CHART,
        )

        # Хитмап навыков
        self.combo_heatmap_n = ft.Dropdown(
            label="Топ",
            value="20",
            dense=True,
            width=100,
            options=[
                ft.DropdownOption(key="10", text="10"),
                ft.DropdownOption(key="20", text="20"),
                ft.DropdownOption(key="30", text="30"),
            ],
        )
        self.btn_heatmap = primary_btn(
            "Построить хитмап", controller.draw_skill_heatmap, icon=ft.Icons.LEADERBOARD
        )
        self.heatmap_placeholder = ft.Text(
            "Нажмите «Построить хитмап», чтобы увидеть топ навыков из ваших вакансий.",
            italic=True,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        _legend = ft.Row(
            spacing=8,
            controls=[
                ft.Text("Грейды:", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Container(
                    content=ft.Text("J — Junior", size=10, color=ft.Colors.BLUE_300),
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.BLUE_300),
                    border_radius=10,
                    padding=ft.Padding(6, 2, 6, 2),
                ),
                ft.Container(
                    content=ft.Text("M — Middle", size=10, color=ft.Colors.INDIGO_400),
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.INDIGO_400),
                    border_radius=10,
                    padding=ft.Padding(6, 2, 6, 2),
                ),
                ft.Container(
                    content=ft.Text(
                        "S — Senior/Lead", size=10, color=ft.Colors.PURPLE_400
                    ),
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.PURPLE_400),
                    border_radius=10,
                    padding=ft.Padding(6, 2, 6, 2),
                ),
            ],
        )
        self.heatmap_box = ft.Column(
            scroll=ft.ScrollMode.AUTO,
            spacing=8,
            expand=True,
            controls=[_legend, self.heatmap_placeholder],
        )

    def build(self, wide: bool = True) -> ft.Control:
        funnel = card(
            ft.Column(
                spacing=10,
                controls=[
                    section_title("Воронка поиска работы", ft.Icons.FILTER_ALT),
                    self.funnel_box,
                ],
            )
        )
        chart = card(
            ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    ft.Row(
                        controls=[
                            section_title("Зарплаты на рынке", ft.Icons.QUERY_STATS),
                            ft.Container(expand=True),
                            self.btn_draw,
                        ]
                    ),
                    self.salary_chart_placeholder,
                    self.salary_stats_row,
                    self.salary_chart_col,
                ],
            ),
            expand=True,
        )
        heatmap = card(
            ft.Column(
                expand=True,
                spacing=10,
                controls=[
                    ft.Row(
                        controls=[
                            section_title("Топ навыков рынка", ft.Icons.LEADERBOARD),
                            ft.Container(expand=True),
                            self.combo_heatmap_n,
                            self.btn_heatmap,
                        ]
                    ),
                    self.heatmap_box,
                ],
            ),
            expand=True,
        )
        if wide:
            bottom = ft.Row(
                expand=True,
                spacing=GAP,
                controls=[
                    ft.Column(expand=1, controls=[chart]),
                    ft.Column(expand=1, controls=[heatmap]),
                ],
            )
        else:
            bottom = ft.Column(expand=True, spacing=GAP, controls=[chart, heatmap])
        return page_column([funnel, bottom])
