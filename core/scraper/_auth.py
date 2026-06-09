"""Авторизация hh.ru — миксин для HHParser."""
import logging
import random


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
        """Быстрая headless-проверка авторизации.

        Переходим на страницу, доступную только авторизованным (/applicant/resumes).
        Если нас перебросило на login — значит сессии нет.
        """
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=True,
            user_agent=random.choice(self.user_agents),
            viewport={"width": 1280, "height": 800},
        )
        try:
            pg = ctx.new_page()
            pg.goto("https://hh.ru/applicant/resumes", wait_until="domcontentloaded", timeout=20000)
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
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=False,
            user_agent=random.choice(self.user_agents),
            viewport={"width": 1280, "height": 800},
        )
        try:
            pg = ctx.new_page()
            pg.goto("https://hh.ru/account/login", wait_until="domcontentloaded", timeout=20000)
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
