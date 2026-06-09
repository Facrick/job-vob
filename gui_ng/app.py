"""app.py — сборка страницы и запуск NiceGUI-приложения (нативное окно).

Точка входа: run_app(). Каждое подключение клиента строит свежий контроллер и
полный UI (для нативного однооконного режима это одна сессия).
"""

import os

from dotenv import load_dotenv
from nicegui import app, ui

from gui_ng import views
from gui_ng.controller import AppController
from gui_ng.theme import apply_theme

# Видимый маркер сборки — бампается при каждой правке, чтобы было видно,
# что запущена свежая версия (а не старый процесс при reload=False).
BUILD_TAG = "build 23 · shadcn-redesign"

_TABS = [
    ("scout", "CRM", "search", views.build_scout_tab),
    ("letters", "Письма", "mail_outline", views.build_letters_tab),
    ("interview", "Интервью", "record_voice_over", views.build_interview_tab),
    ("analytics", "Аналитика", "bar_chart", views.build_analytics_tab),
    ("handbook", "Учебник", "menu_book", views.build_handbook_tab),
    ("logs", "Логи", "terminal", views.build_logs_tab),
]


@ui.page("/")
def index():
    apply_theme()
    c = AppController()

    # Убираем стандартные отступы/зазоры контейнера NiceGUI — иначе h-screen
    # суммируется с padding и страница выходит за вьюпорт (лишний скролл).
    ui.query(".nicegui-content").style(
        "height:100vh; padding:0; gap:0; overflow:hidden; flex-wrap:nowrap"
    )

    # Оболочка приложения: слева — навигация, справа — контент.
    with ui.row().classes("w-full h-full no-wrap gap-0"):
        # ── Сайдбар ───────────────────────────────────────────
        with ui.column().classes("vob-rail h-full no-wrap gap-0").style(
            "width:216px;min-width:216px;"
            "background:#0c0c0e;"
            "border-right:1px solid #1f1f23;"
            "transition:width .18s cubic-bezier(.4,0,.2,1)"
        ) as sidebar:
            # ── Логотип / заголовок ────────────────────────────
            with ui.row().classes("items-center gap-2 px-3 py-3 no-wrap w-full"):
                ui.button(icon="menu", on_click=lambda: _toggle_rail()).props(
                    "flat round dense"
                ).style("color:#71717a").tooltip("Свернуть/развернуть")
                with ui.column().classes("gap-0 vob-rail-hide"):
                    ui.label("QA Assistant").classes(
                        "text-sm font-semibold leading-tight"
                    ).style("color:#fafafa;letter-spacing:-.01em")
                    ui.label("Pro · Job CRM").classes(
                        "text-xs leading-tight"
                    ).style("color:#52525b")
            ui.separator().style("opacity:.4")
            # ── Навигационные вкладки ──────────────────────────
            with ui.tabs().props(
                "vertical no-caps inline-label active-color=primary "
                "indicator-color=transparent"
            ).classes("w-full flex-grow").style("padding:4px 0") as tabs:
                for name, label, icon, _ in _TABS:
                    ui.tab(name, label=label, icon=icon).classes("justify-start")
            c.tabs = tabs
            ui.separator().style("opacity:.4")
            # ── Build tag ──────────────────────────────────────
            ui.label("build 23").classes("vob-rail-hide").style(
                "font-size:11px;color:#3f3f46;padding:6px 14px;letter-spacing:.03em"
            )

        rail = {"collapsed": False}

        def _toggle_rail():
            rail["collapsed"] = not rail["collapsed"]
            sidebar.classes(
                add="vob-collapsed" if rail["collapsed"] else "",
                remove="" if rail["collapsed"] else "vob-collapsed",
            )

        # ── Контент ───────────────────────────────────────────
        with ui.tab_panels(tabs, value="scout").props("vertical keep-alive").classes(
            "flex-grow h-full"
        ).style("background:#09090b"):
            for name, _, _, builder in _TABS:
                with ui.tab_panel(name).classes("p-3 h-full"):
                    builder(c)

    c.on_ready()


def run_app():
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(dotenv_path=dotenv_path)

    native = os.getenv("VOB_BROWSER", "").lower() not in ("1", "true", "yes")
    kwargs = dict(
        title="QA Smart Assistant Pro | Job CRM",
        reload=False,
        storage_secret="job-vob-ng",
    )
    port = os.getenv("VOB_PORT")
    if port:
        kwargs["port"] = int(port)
    if native:
        # Иконку окна Windows winforms-бэкенд pywebview берёт из start(icon=...);
        # прозрачный .ico = пустой значок в заголовке (иначе берётся иконка python.exe).
        blank_ico = os.path.join(os.path.dirname(__file__), "assets", "blank.ico")
        if os.path.isfile(blank_ico):
            app.native.start_args["icon"] = blank_ico
        ui.run(native=True, window_size=(1320, 860), show=False, **kwargs)
    else:
        ui.run(native=False, show=False, **kwargs)
