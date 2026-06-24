"""app.py — сборка страницы и запуск NiceGUI-приложения (нативное окно).

Точка входа: run_app(). Каждое подключение клиента строит свежий контроллер и
полный UI (для нативного однооконного режима это одна сессия).
"""

import os

from dotenv import load_dotenv
from nicegui import app, ui

from core.backup import backup_database
from core.paths import user_path

from gui_ng import views  # noqa: F401 – re-exported from gui_ng/views/__init__.py
from gui_ng.controller import AppController
from gui_ng.theme import apply_theme

BUILD_TAG = "build 27"
APP_TITLE = "Job VOB · IT Career OS"

# (name, label, icon, builder, alpha, section)
# section: str = заголовок секции перед этим пунктом, None = без заголовка
_TABS = [
    ("scout",     "CRM",       "grid_view",        views.build_scout_tab,     False, "ANALYTICS"),
    ("letters",   "Письма",    "mail_outline",      views.build_letters_tab,   False, None),
    ("interview", "Интервью",  "record_voice_over", views.build_interview_tab, False, None),
    ("analytics", "Аналитика", "bar_chart",         views.build_analytics_tab, True,  None),
    ("handbook",  "Учебник",   "menu_book",         views.build_handbook_tab,  True,  None),
    ("logs",      "Логи",      "terminal",          views.build_logs_tab,      False, "TOOLS"),
    ("settings",  "Настройки", "settings",          views.build_settings_tab,  False, None),
]


@ui.page("/")
def index():
    apply_theme()

    ui.add_body_html(
        "<script>"
        "setTimeout(function(){"
        "  if(!document.querySelector('.vob-rail')){"
        "    console.warn('[watchdog] UI не отрендерился — перезагрузка');"
        "    window.location.reload();"
        "  }"
        "}, 4000);"
        "</script>"
    )

    c = AppController()

    ui.query(".nicegui-content").style(
        "height:100vh; padding:0; gap:0; overflow:hidden; flex-wrap:nowrap"
    )

    with ui.row().classes("w-full h-full no-wrap gap-0"):
        # ── Сайдбар ───────────────────────────────────────────────────
        with ui.column().classes("vob-rail h-full no-wrap gap-0").style(
            "width:200px;min-width:200px;position:relative;z-index:5;"
            "background:rgba(14,14,19,.92);"
            "backdrop-filter:blur(16px) saturate(1.1);"
            "border-right:1px solid rgba(255,255,255,.06);"
            "transition:width .18s cubic-bezier(.4,0,.2,1)"
        ) as sidebar:

            # Логотип
            with ui.row().classes("items-center gap-2 px-3 py-3 no-wrap w-full"):
                ui.button(icon="menu", on_click=lambda: _toggle_rail()).props(
                    "flat dense"
                ).classes("vob-rail-burger").tooltip("Свернуть/развернуть")
                with ui.column().classes("gap-0 vob-rail-hide"):
                    ui.label("Job VOB").classes("text-sm font-semibold leading-tight").style(
                        "color:#fafafa;letter-spacing:-.01em"
                    )
                    ui.label("IT Career OS").classes("text-xs leading-tight").style(
                        "color:#52525b"
                    )

            ui.separator().style("opacity:.3;margin:0 12px")

            # Навигация с секциями
            with ui.tabs().props(
                "vertical no-caps inline-label active-color=primary "
                "indicator-color=transparent"
            ).classes("w-full flex-grow").style("padding:6px 0") as tabs:

                current_section = None
                for name, label, icon, _, alpha, section in _TABS:
                    if section and section != current_section:
                        current_section = section
                        ui.label(section).classes("vob-rail-section vob-rail-hide")
                    with ui.tab(name, label=label, icon=icon).classes("justify-start"):
                        if alpha:
                            ui.label("alpha").classes(
                                "vob-alpha-chip vob-rail-hide"
                            ).tooltip("Экспериментальная функция")

            c.tabs = tabs

            ui.separator().style("opacity:.25;margin:0 12px")

            ui.label(BUILD_TAG).classes("vob-rail-hide").style(
                "font-size:10px;color:#3f3f46;padding:8px 14px 10px;"
                "letter-spacing:.03em;white-space:nowrap;overflow:hidden"
            )

        rail = {"collapsed": False}

        def _toggle_rail():
            rail["collapsed"] = not rail["collapsed"]
            sidebar.classes(
                add="vob-collapsed" if rail["collapsed"] else "",
                remove="" if rail["collapsed"] else "vob-collapsed",
            )

        # ── Контент ───────────────────────────────────────────────────
        with ui.tab_panels(tabs, value="scout").props("vertical keep-alive").classes(
            "flex-grow h-full"
        ).style("background:transparent"):
            for name, _, _, builder, _alpha, _section in _TABS:
                with ui.tab_panel(name).classes("p-3 h-full"):
                    builder(c)

    c.on_ready()


def run_app():
    dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    load_dotenv(dotenv_path=dotenv_path)

    backup_database(user_path("data/app.db"))

    native = os.getenv("VOB_BROWSER", "").lower() not in ("1", "true", "yes")
    kwargs = dict(
        title=APP_TITLE,
        reload=False,
        storage_secret="job-vob-ng",
    )
    port = os.getenv("VOB_PORT")
    if port:
        kwargs["port"] = int(port)
    if native:
        blank_ico = os.path.join(os.path.dirname(__file__), "assets", "blank.ico")
        if os.path.isfile(blank_ico):
            app.native.start_args["icon"] = blank_ico
        ui.run(native=True, window_size=(1320, 860), show=False, **kwargs)
    else:
        ui.run(native=False, show=False, **kwargs)
