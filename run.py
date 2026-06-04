"""run.py — точка входа приложения (NiceGUI, нативное окно через pywebview).

Поставьте переменную окружения VOB_BROWSER=1, чтобы открыть в браузере вместо
нативного окна (удобно при отладке), VOB_PORT — задать порт.
"""

from gui_ng.app import run_app

if __name__ in {"__main__", "__mp_main__"}:
    run_app()
