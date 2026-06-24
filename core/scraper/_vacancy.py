"""Парсинг вакансий с hh.ru — миксин для HHParser."""
import logging
import random
import re
import time
from collections.abc import Callable
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from playwright.sync_api import Page

from core.scraper._constants import (
    HH_BASE_URL,
    HH_VACANCY_URL,
    TIMEOUT_PAGE_LOAD_MS,
    TIMEOUT_PAGE_LOAD_SLOW_MS,
    TIMEOUT_SELECTOR_MS,
)
from core.utils import parse_salary_text


class _VacancyMixin:
    """Методы поиска и разбора карточек вакансий на hh.ru."""

    # Узкие фразы, которые встречаются ТОЛЬКО на странице капчи/блокировки.
    CAPTCHA_TITLE_MARKERS = [
        "captcha",
        "доступ ограничен",
        "access denied",
        "are you a robot",
        "доступ временно ограничен",
    ]
    # Реальные DOM-селекторы виджетов капчи hh.ru / Yandex SmartCaptcha.
    CAPTCHA_SELECTORS = [
        "div.captcha",
        "[data-qa='captcha']",
        "iframe[src*='captcha']",
        ".smart-captcha",
        "[id*='smartcaptcha']",
        "form[action*='captcha']",
    ]
    # Маркеры в URL, на который hh.ru редиректит при блокировке.
    CAPTCHA_URL_MARKERS = ["/captcha", "captcha_key", "/blocked"]
    # Маркеры vpncheck-страницы hh.ru (анти-бот редирект при ВПН).
    VPNCHECK_URL_MARKERS = ["vpncheeck", "vpncheck"]

    def _abort_heavy_resources(self, route) -> None:
        url = route.request.url.lower()
        blocked_keywords = [
            "metrika", "google-analytics", "analytics",
            "adv", "banner", "doubleclick", "facebook",
            "tracking", "pixel", "hotjar",
        ]
        if any(keyword in url for keyword in blocked_keywords):
            route.abort()
        else:
            route.continue_()

    def _is_captcha_page(self, page: Page) -> bool:
        """Определяет страницу капчи/блокировки по надёжным признакам."""
        try:
            url = page.url.lower()
            if any(marker in url for marker in self.CAPTCHA_URL_MARKERS):
                return True
            for selector in self.CAPTCHA_SELECTORS:
                try:
                    if page.locator(selector).count() > 0:
                        return True
                except Exception:
                    continue
            title = page.title().lower()
            if any(marker in title for marker in self.CAPTCHA_TITLE_MARKERS):
                return True
            return False
        except Exception:
            return False

    def _looks_like_captcha_error(self, error_msg: str) -> bool:
        """Проверяет, относится ли текст ошибки к капче (а не к обычному багу)."""
        msg = error_msg.lower()
        return "captcha" in msg or "капча" in msg or "доступ ограничен" in msg

    def _is_blocked_page(self, page: Page) -> bool:
        """Возвращает True если страница — vpncheck или капча."""
        try:
            url = page.url.lower()
            if any(m in url for m in self.VPNCHECK_URL_MARKERS):
                return True
        except Exception:
            pass
        return self._is_captcha_page(page)

    def _wait_for_unblock(self, page: Page, target_url: str, *,
                          timeout_ms: int = 180_000) -> None:
        """Ждёт пока пользователь пройдёт капчу/vpncheck в открытом окне браузера.

        Вызывать только когда браузер уже visible (не headless).
        После прохождения проверки переходит на target_url.
        Бросает RuntimeError при таймауте.
        """
        logging.warning(
            "⚠️  hh.ru заблокировал запрос (VPN/капча). "
            "Пройдите проверку в открытом окне браузера — "
            f"у вас {timeout_ms // 1000} секунд."
        )
        try:
            page.wait_for_function(
                "(url => !url.includes('vpncheeck') && !url.includes('vpncheck') "
                "       && !url.includes('/captcha') && !url.includes('captcha_key'))"
                "(window.location.href)",
                timeout=timeout_ms,
            )
        except Exception:
            raise RuntimeError(
                f"Таймаут ожидания прохождения проверки hh.ru ({timeout_ms // 1000} с). "
                "Попробуйте снова."
            ) from None
        logging.info("✅ Проверка пройдена, продолжаю…")
        # Небольшая пауза перед переходом чтобы hh.ru зафиксировал куки
        page.wait_for_timeout(2000)
        page.goto(target_url, wait_until="networkidle", timeout=TIMEOUT_PAGE_LOAD_SLOW_MS)
        try:
            page.wait_for_selector("a[href*='/vacancy/']", timeout=10000, state="attached")
        except Exception:
            pass

    def parse_market(
        self,
        text: str = "",
        period: int = 1,
        area: int = 113,
        experience: str = "between1And3",
        schedule: str = "",
        page_limit: int = 1,
        search_field: str = "name,company_name,description",
        progress_callback: Callable | None = None,
        max_vacancies: int | None = None,
        on_vacancy: Callable | None = None,
        should_cancel: Callable[[], bool] | None = None,
        headless: bool | None = None,
    ) -> list[dict]:
        from playwright.sync_api import sync_playwright

        def _cancelled() -> bool:
            return bool(should_cancel and should_cancel())

        # Дедупликация только в пределах текущего запуска парсера.
        # Фильтрацию уже сохранённых вакансий делает GUI-слой (on_vacancy),
        # иначе повторный поиск находил бы почти ноль новых вакансий.
        seen_ids: set = set()
        discovered_links = []

        if not max_vacancies:
            max_vacancies = 200  # мягкий потолок для парсера

        # page_limit=0 означает «без ограничений»; используем большое число как потолок
        effective_page_limit = page_limit if page_limit > 0 else 50

        with sync_playwright() as p:
            # Если в прошлый раз получили vpncheck/капчу — сразу стартуем visible.
            # headless=None → берём значение из конфига; явный bool из GUI имеет приоритет.
            if headless is None:
                headless = self.headless
            mode = "headless (без окна)" if headless else "с видимым окном"
            logging.info(f"🔍 Поиск вакансий по запросу «{text}» — режим {mode}")

            context = self._launch_context(p, headless=headless)
            page = context.new_page()
            page.route("**/*", self._abort_heavy_resources)

            try:
                for current_page in range(effective_page_limit):
                    if _cancelled():
                        logging.info("🛑 Сбор ссылок остановлен пользователем.")
                        break
                    if len(discovered_links) >= max_vacancies:
                        break

                    # search_field по умолчанию name,company_name,description —
                    # как при ручном поиске на hh.ru, иначе находится в разы меньше
                    # вакансий (совпадение только в заголовке отсекает большинство).
                    search_url = (
                        f"{HH_BASE_URL}/search/vacancy?text={quote_plus(text)}"
                        f"&search_field={quote_plus(search_field)}"
                        f"&area={area}&search_period={period}"
                        f"&items_on_page=20&page={current_page}"
                    )
                    # experience пустой → hh.ru не фильтрует по опыту (любой опыт)
                    if experience:
                        search_url += f"&experience={experience}"
                    if schedule:
                        search_url += f"&schedule={schedule}"
                    logging.info(f"🌐 GET {search_url}")

                    logging.info(f"📄 Открываю страницу результатов {current_page + 1}/{page_limit}")
                    page.goto(
                        search_url,
                        timeout=self.config.get("browser_timeout_ms"),
                        wait_until="domcontentloaded",
                    )

                    if self._is_blocked_page(page):
                        if headless:
                            # Переоткрываем браузер в видимом режиме чтобы пользователь
                            # мог пройти капчу/vpncheck вручную.
                            logging.warning(
                                "⚠️  hh.ru заблокировал запрос в headless-режиме. "
                                "Переключаюсь на видимый браузер…"
                            )
                            context.close()
                            headless = False
                            context = self._launch_context(p, headless=False)
                            page = context.new_page()
                            page.route("**/*", self._abort_heavy_resources)
                            page.goto(
                                search_url,
                                timeout=self.config.get("browser_timeout_ms"),
                                wait_until="domcontentloaded",
                            )
                        if self._is_blocked_page(page):
                            self._wait_for_unblock(page, search_url)

                    self.human_engine.move_mouse_randomly(page)
                    self.human_engine.random_scroll(page)
                    self.human_engine.apply_adaptive_delay(page)

                    # Ждём появления карточек вакансий (JS-рендеринг)
                    try:
                        page.wait_for_selector(
                            "a[href*='/vacancy/']",
                            timeout=15000,
                            state="attached",
                        )
                    except Exception:
                        logging.warning("⚠️ Карточки вакансий не появились за 15 сек — парсим как есть")

                    soup = BeautifulSoup(page.content(), "html.parser")

                    links_found = soup.find_all("a", href=re.compile(r"/vacancy/\d+"))
                    logging.info(f"🔗 Найдено ссылок на вакансии на странице: {len(links_found)}")

                    new_on_page = 0
                    for link in links_found:
                        match = re.search(r"/vacancy/(\d+)", link.get("href", ""))
                        if match:
                            v_id = match.group(1)
                            v_name = link.get_text(strip=True)
                            if v_id not in seen_ids and len(v_name) >= 3:
                                if "responses" not in link.get("href", ""):
                                    seen_ids.add(v_id)
                                    discovered_links.append({"id": v_id, "name": v_name})
                                    new_on_page += 1
                                    if len(discovered_links) >= max_vacancies:
                                        break

                    # Если на странице не появилось ни одной новой ссылки —
                    # значит результаты закончились, дальше листать незачем.
                    if new_on_page == 0:
                        logging.info("📭 Новых вакансий на странице нет — завершаю постраничный обход.")
                        break

                total = len(discovered_links)
                logging.info(f"🆕 Найдено новых вакансий: {total}. Начинаю детальный разбор...")

                final_vacancies = []
                for idx, v in enumerate(discovered_links, 1):
                    if _cancelled():
                        logging.info("🛑 Детальный разбор остановлен пользователем.")
                        break
                    label = v["name"][:60]
                    logging.info(f"⏳ [{idx}/{total}] Обрабатываю: {label}")
                    if progress_callback:
                        progress_callback(idx, total, label)
                    try:
                        vacancy_info = self._parse_vacancy_detail(page, v["id"], v["name"])
                        if vacancy_info:
                            vd = vacancy_info.to_dict()
                            final_vacancies.append(vd)
                            logging.info(
                                f"✅ [{idx}/{total}] Сохранено: {vacancy_info.company} — {label}"
                            )
                            if on_vacancy:
                                on_vacancy(dict(vd))
                    except Exception as e:
                        if self._looks_like_captcha_error(str(e)):
                            logging.warning(f"⚠️ Капча на вакансии {v['id']}. Пауза 30 сек...")
                            time.sleep(30)
                        else:
                            logging.error(f"❌ Ошибка разбора вакансии {v['id']}: {e}")
                    # Короткая пауза между карточками — снижает риск капчи,
                    # но заметно быстрее прежних 2–5 сек.
                    time.sleep(random.uniform(0.5, 1.2))

                logging.info(f"🏁 Готово. Успешно разобрано: {len(final_vacancies)} из {total}")
                return final_vacancies

            finally:
                context.close()

    def _parse_vacancy_detail(
        self, page: Page, vacancy_id: str, title: str
    ):
        url = HH_VACANCY_URL.format(vacancy_id=vacancy_id)
        logging.debug(f"Парсинг карточки: {url}")

        try:
            page.goto(url, timeout=TIMEOUT_PAGE_LOAD_MS, wait_until="domcontentloaded")
        except Exception as e:
            logging.warning(f"Не удалось загрузить вакансию {vacancy_id}: {e}")
            return None

        if self._is_captcha_page(page):
            raise Exception(f"Обнаружена капча на странице вакансии {vacancy_id}")

        try:
            page.wait_for_selector(
                "[data-qa='vacancy-title']", timeout=TIMEOUT_SELECTOR_MS, state="attached"
            )
        except Exception:
            logging.debug(f"Заголовок вакансии {vacancy_id} не дождались, парсим как есть")

        self.human_engine.move_mouse_randomly(page)
        self.human_engine.random_scroll(page)
        self.human_engine.apply_adaptive_delay(page)

        return self._build_vacancy_info(page.content(), vacancy_id, title)

    @classmethod
    def _build_vacancy_info(cls, html: str, vacancy_id: str, title: str):
        """Извлекает VacancyInfo из HTML карточки вакансии.

        Чистая функция от HTML — общая для sync и async парсера (тот лишь
        получает page.content() по-разному).
        """
        from core.scraper._human import VacancyInfo

        soup = BeautifulSoup(html, "html.parser")

        company = cls._safe_extract(
            soup,
            lambda s: (
                s.find(attrs={"data-qa": "vacancy-company-name"})
                or s.select_one("[class*='company-name']")
            ),
            default="Не указана",
        )

        description = cls._safe_extract(
            soup,
            lambda s: (
                s.find(attrs={"data-qa": "vacancy-description"})
                or s.select_one(".g-user-content")
            ),
            default="Описание отсутствует.",
            separator="\n",
        )

        salary_text = cls._safe_extract(
            soup, lambda s: s.find(attrs={"data-qa": "vacancy-salary"}), default=""
        )
        salary_min, salary_max = parse_salary_text(salary_text)

        try:
            skills_tags = soup.find_all(attrs={"data-qa": "bloko-tag__text"})
            skills_list = [skill.get_text(strip=True) for skill in skills_tags]
            skills_str = ", ".join(skills_list) if skills_list else "Не указаны"
        except Exception:
            skills_str = "Не указаны"

        return VacancyInfo(
            id=vacancy_id,
            title=title,
            company=company,
            salary_min=salary_min,
            salary_max=salary_max,
            description=description,
            skills=skills_str,
            url=HH_VACANCY_URL.format(vacancy_id=vacancy_id),
        )

    @staticmethod
    def _safe_extract(soup, finder, default: str = "", separator: str = "") -> str:
        """Безопасно извлекает текст из тега, найденного finder(soup)."""
        try:
            tag = finder(soup)
            if not tag:
                return default
            if separator:
                return tag.get_text(separator=separator, strip=True)
            return tag.get_text(strip=True)
        except Exception:
            return default
