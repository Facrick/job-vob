"""Точка входа для собранного .exe (PyInstaller one-file).

Зачем отдельный файл, а не gui_ng/app.py:
1. В one-file сборке gui_ng/app.py:run_app() ищет .env по пути относительно
   __file__, который указывает во временную распаковку — путь ломается.
   Здесь мы грузим .env, вшитый в сборку, из sys._MEIPASS до старта приложения.
2. Playwright в собранном виде должен знать, где лежит вшитый Chromium —
   задаём PLAYWRIGHT_BROWSERS_PATH на папку браузеров внутри _MEIPASS.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def _bundle_dir() -> Path:
    """Папка распаковки PyInstaller (_MEIPASS) либо корень проекта в dev."""
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(__file__).resolve().parent


def _bootstrap_env() -> None:
    bundle = _bundle_dir()

    # 1. API-ключи: .env вшит в сборку как data-файл (см. job-vob.spec).
    #    override=False — если рядом с .exe положить свой .env, он приоритетнее
    #    через ручную загрузку ниже.
    bundled_env = bundle / ".env"
    if bundled_env.is_file():
        load_dotenv(dotenv_path=bundled_env, override=False)

    # Пользовательский .env рядом с .exe (если есть) — перекрывает вшитый.
    if getattr(sys, "frozen", False):
        external_env = Path(sys.executable).resolve().parent / ".env"
        if external_env.is_file():
            load_dotenv(dotenv_path=external_env, override=True)

    # 2. Playwright: указываем путь к вшитому браузеру.
    if getattr(sys, "frozen", False):
        browsers = bundle / "ms-playwright"
        if browsers.is_dir():
            os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))


def main() -> None:
    _bootstrap_env()
    # Импортируем приложение ПОСЛЕ загрузки окружения — модули AI читают
    # ключи из os.getenv на этапе инициализации клиента.
    from gui_ng.app import run_app
    run_app()


if __name__ == "__main__":
    main()
