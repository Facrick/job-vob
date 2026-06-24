"""conftest.py — общие фикстуры pytest (автоматически подхватывается).

Здесь живёт фикстура `app_server`: запускает приложение job-vob в браузерном
режиме на отдельном порту, ждёт его готовности и отдаёт URL тестам. После
тестов гасит сервер. Тесту достаточно попросить фикстуру — вся возня скрыта.
"""
import os
import subprocess
import sys
import time

import pytest
from pages.analytics_page import AnalyticsPage

# Отдельный порт для тестов — чтобы не конфликтовать с твоим рабочим окном (8080).
TEST_PORT = 8099
BASE_URL = f"http://localhost:{TEST_PORT}"


def _server_ready(url: str) -> bool:
    """Проверяет, отвечает ли HTTP-сервер по URL (надёжнее проверки порта:
    работает и для localhost/IPv6, и ждёт реальной готовности веб-сервера)."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=1) as resp:
            return resp.status == 200
    except (urllib.error.URLError, ConnectionError, OSError):
        return False


@pytest.fixture(scope="session")
def app_server():
    """Запускает приложение на TEST_PORT в фоне на всё время тест-сессии.

    scope="session" — поднимаем приложение ОДИН раз на все тесты (не на каждый),
    иначе каждый тест ждал бы старта сервера ~несколько секунд.
    """
    # Окружение для дочернего процесса: браузерный режим + наш порт.
    env = dict(os.environ, VOB_BROWSER="1", VOB_PORT=str(TEST_PORT))
    # NiceGUI, видя pytest в окружении, уходит во встроенный «screen test»
    # режим и требует NICEGUI_SCREEN_TEST_PORT. Нам он не нужен — мы тестируем
    # приложение снаружи через Playwright. Вычищаем pytest-маркеры из дочернего
    # окружения, чтобы NiceGUI стартовал как обычный веб-сервер.
    for var in ("PYTEST_CURRENT_TEST", "PYTEST_VERSION", "NICEGUI_SCREEN_TEST_PORT"):
        env.pop(var, None)
    env["NICEGUI_STORAGE_PATH"] = env.get("NICEGUI_STORAGE_PATH", ".nicegui")

    # Запускаем `python run.py` отдельным процессом (как обычный старт приложения).
    root = os.path.dirname(os.path.dirname(__file__))  # корень проекта
    proc = subprocess.Popen(
        [sys.executable, "run.py"],
        env=env,
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    # Ждём, пока сервер реально поднимется (до 30 секунд).
    deadline = time.time() + 30
    while time.time() < deadline:
        if proc.poll() is not None:
            out = proc.stdout.read().decode("utf-8", "replace") if proc.stdout else ""
            pytest.fail(f"Процесс приложения упал (код {proc.returncode}):\n{out}")
        if _server_ready(BASE_URL):
            break
        time.sleep(0.3)
    else:
        proc.terminate()
        pytest.fail(f"Приложение не поднялось на порту {TEST_PORT} за 30с")

    # Небольшая пауза — дать NiceGUI дорендериться после открытия порта.
    time.sleep(1.5)

    
    # `yield` отдаёт значение тесту и «замораживает» фикстуру тут.
    # Всё, что ПОСЛЕ yield — выполнится после тестов (очистка).
    yield BASE_URL

    # Очистка: гасим процесс приложения.
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

@pytest.fixture
def analytics_page(page, app_server):
    """Переходим на страницу аналитики и ждём, пока она отрендерится."""
    analytics_page = AnalyticsPage(page)
    analytics_page.open(app_server)
    yield analytics_page
        