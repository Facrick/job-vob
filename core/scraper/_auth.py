"""Авторизация hh.ru — миксин для HHParser."""
import logging
import random
from pathlib import Path

from core.scraper._constants import (
    HH_LOGIN_URL,
    HH_RESUMES_URL,
    TIMEOUT_AUTH_MS,
    TIMEOUT_SELECTOR_FAST_MS,
)


def _clear_chromium_locks(user_data_dir: str) -> None:
    """Удаляет lock-файлы Chromium перед запуском.

    При переносе профиля между машинами (Windows→Docker) Chromium оставляет
    SingletonLock/SingletonCookie с hostname старой машины — новый процесс
    отказывается стартовать с exitCode=21.

    SingletonLock — симлинк на Linux, поэтому проверяем через os.path.lexists
    и удаляем os.unlink (работает для симлинков независимо от цели).
    Также чистим поддиректории профилей (Default/, Profile 1/, и т.д.).
    """
    import os

    root = Path(user_data_dir)
    lock_names = ("SingletonLock", "SingletonCookie", "SingletonSocket")

    # Корень user_data_dir
    dirs_to_clean = [root]

    # Поддиректории профилей: Default, Profile 1, Profile 2, ...
    if root.exists():
        for child in root.iterdir():
            if child.is_dir() and (
                child.name == "Default"
                or (child.name.startswith("Profile ") and child.name[8:].isdigit())
            ):
                dirs_to_clean.append(child)

    for d in dirs_to_clean:
        for name in lock_names:
            p = d / name
            try:
                # lexists возвращает True даже для битых симлинков
                if os.path.lexists(str(p)):
                    os.unlink(str(p))
                    logging.info(f"[Auth] Удалён lock-файл: {p}")
            except Exception as e:
                logging.warning(f"[Auth] Не удалось удалить {p}: {e}")


class _AuthMixin:
    """Методы проверки и выполнения авторизации на hh.ru."""

    # Селекторы элементов, которые видны ТОЛЬКО у авторизованного пользователя.
    _LOGGED_IN_SELECTORS = [
        '[data-qa="account-menu-item"]',
        '[data-qa="mainmenu_myResume"]',
        '.supernova-navi-item_account',
        '[data-qa="user-menu-toggle"]',
    ]
    # Селекторы кнопки входа — видны только у гостя.
    _LOGIN_BTN_SELECTORS = [
        '[data-qa="account-login-link"]',
        'a[href*="/account/login"]',
    ]

    def check_auth_status(self) -> bool:
        """Публичная проверка авторизации на hh.ru (запускает headless Playwright).

        Вызывается из UI-контроллера в фоне. Возвращает True если сессия активна.
        """
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return self._check_logged_in(p)

    def _check_logged_in(self, p) -> bool:
        """Headless-проверка авторизации по странице, требующей логина.

        Открываем /applicant/resumes — она доступна ТОЛЬКО залогиненным.
        Если сессии нет, hh.ru редиректит на /account/login (с backurl).
        Это надёжнее, чем искать JS-меню аккаунта на главной: оно
        дорисовывается скриптом уже после domcontentloaded, и быстрая проверка
        ловила пустой DOM → ложный «не авторизован».
        """
        ctx = self._launch_context(p, headless=True)
        try:
            pg = ctx.new_page()
            pg.goto(HH_RESUMES_URL, wait_until="domcontentloaded", timeout=TIMEOUT_AUTH_MS)

            # Редирект на форму логина — сессии нет.
            if "/account/login" in pg.url:
                return False

            # Остались на странице резюме — даём JS дорисовать и проверяем
            # маркер залогиненного пользователя как подтверждение.
            for sel in self._LOGGED_IN_SELECTORS:
                try:
                    pg.wait_for_selector(sel, timeout=TIMEOUT_SELECTOR_FAST_MS)
                    return True
                except Exception:
                    continue

            # Маркеры меню не появились, но и на логин не выкинуло — раз
            # /applicant/resumes открылась без редиректа, считаем сессию живой.
            return "/account/login" not in pg.url
        except Exception as e:
            logging.warning(f"[Auth-Check] Не удалось проверить сессию: {e}")
            return False
        finally:
            ctx.close()

    def _login_in_browser(self, p) -> bool:
        """Открывает ВИДИМЫЙ браузер для ручного входа на hh.ru.

        Ждёт, пока URL уйдёт со страницы /account/login (признак успешного входа),
        затем закрывает окно. Сессия сохраняется в persistent user_data_dir и
        будет доступна следующим headless-запускам.
        """
        logging.info("🔑 Открываю окно браузера для входа на hh.ru...")
        ctx = self._launch_context(p, headless=False)
        try:
            pg = ctx.new_page()
            pg.goto(HH_LOGIN_URL, wait_until="domcontentloaded", timeout=TIMEOUT_AUTH_MS)
            logging.info("⏳ Войдите в аккаунт hh.ru в открывшемся окне (у вас 3 минуты)...")
            pg.wait_for_url(
                lambda url: "/account/login" not in url,
                timeout=180_000,
            )
            pg.wait_for_timeout(2000)
            logging.info("✅ Авторизация выполнена. Закрываю окно и продолжаю в фоне...")
            return True
        except Exception as e:
            logging.warning(f"⚠️ Авторизация не завершена: {e}")
            return False
        finally:
            ctx.close()
