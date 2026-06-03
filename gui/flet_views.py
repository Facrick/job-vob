"""flet_views.py — UI для Flet 0.85+

Главный вид приложения (MainView), который собирает вместе все вкладки
из директории gui/views.

Layout-правила (проверено эмпирически):
  • НЕ ставить expand=True у ребёнка внутри Row(wrap=True)  → серый экран.
  • НЕ ставить expand=True у ребёнка внутри scroll-контейнера → серый экран.
  • НЕ класть Row внутрь Row(wrap=True) → серый экран.
  • Прокрутка — через ListView/Row/Column(scroll=AUTO).
"""

import flet as ft

from gui.components import BREAKPOINT
from gui.analytics_tab import AnalyticsTabView
from gui.handbook_tab import HandbookTabView
from gui.interview_tab import InterviewTabView
from gui.letters_tab import LettersTabView
from gui.logs_tab import LogsTabView
from gui.scout_tab import ScoutTabView


# ──────────────────────────────────────────────────────────────
#  Главное окно
# ──────────────────────────────────────────────────────────────
class MainView:
    def __init__(self, controller):
        self.controller = controller
        self._page: ft.Page | None = None

        self.scout_tab = ScoutTabView(controller)
        self.letters_tab = LettersTabView(controller)
        self.interview_tab = InterviewTabView(controller)
        self.analytics_tab = AnalyticsTabView(controller)
        self.handbook_tab = HandbookTabView(controller.handbook_ctl)
        self.logs_tab = LogsTabView(controller)

        self._tab_views = [
            self.scout_tab,
            self.letters_tab,
            self.interview_tab,
            self.analytics_tab,
            self.handbook_tab,
            self.logs_tab,
        ]
        self._index = 0
        self._wide = True

        self.body = ft.Container(
            content=self._tab_views[0].build(self._wide),
            expand=True,
            padding=ft.Padding(16, 12, 16, 8),
        )

        self.nav_bar = ft.NavigationBar(
            selected_index=0,
            on_change=self._on_nav_change,
            height=58,
            label_behavior=ft.NavigationBarLabelBehavior.ONLY_SHOW_SELECTED,
            destinations=[
                ft.NavigationBarDestination(icon=ft.Icons.SEARCH, label="CRM"),
                ft.NavigationBarDestination(icon=ft.Icons.MAIL_OUTLINE, label="Письма"),
                ft.NavigationBarDestination(
                    icon=ft.Icons.RECORD_VOICE_OVER, label="Интервью"
                ),
                ft.NavigationBarDestination(icon=ft.Icons.BAR_CHART, label="Аналитика"),
                ft.NavigationBarDestination(
                    icon=ft.Icons.BOOK_OUTLINED, label="Учебник"
                ),
                ft.NavigationBarDestination(icon=ft.Icons.TERMINAL, label="Логи"),
            ],
        )

    def _header(self) -> ft.Control:
        return ft.Container(
            padding=ft.Padding(20, 14, 20, 14),
            content=ft.Row(
                spacing=14,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                controls=[
                    ft.Container(
                        width=44,
                        height=44,
                        border_radius=12,
                        bgcolor=ft.Colors.INDIGO,
                        alignment=ft.Alignment(0, 0),
                        content=ft.Icon(ft.Icons.WORK, color=ft.Colors.WHITE, size=24),
                    ),
                    ft.Column(
                        spacing=0,
                        controls=[
                            ft.Text(
                                "QA Smart Assistant Pro",
                                size=20,
                                weight=ft.FontWeight.BOLD,
                            ),
                            ft.Text(
                                "Поиск вакансий · письма · собеседования",
                                size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                    ),
                ],
            ),
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
            ft.Column(
                expand=True,
                spacing=0,
                controls=[self._header(), ft.Divider(height=1, thickness=1), self.body],
            )
        ]
        self._render_active()
        page.update()
