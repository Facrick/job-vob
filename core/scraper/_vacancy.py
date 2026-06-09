"""Парсинг вакансий с hh.ru — миксин для HHParser."""
import logging
import random
import re
import time
from collections.abc import Callable

from bs4 import BeautifulSoup
from playwright.sync_api import Page

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

    def _get_seen_ids(self) -> set:
        try:
            from core.database import VacancyRepository
            repo = VacancyRepository()
            vacancies = repo.get_vacancies_filtered("all")
            return {v["id"] for v in vacancies}
        except Exception as e:
            logging.warning(f"Не удалось загрузить существующие ID: {e}")
            return set()

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

    def parse_market(
        self,
        text: str = "QA Engineer",
        period: int = 1,
        area: int = 113,
        experience: str = "between1And3",
        schedule: str = "remote",
        page_limit: int = 1,
        progress_callback: Callable | None = None,
        max_vacancies: int | None = None,
        on_vacancy: Callable | None = None,
    ) -> list[dict]:
        from playwright.sync_api import sync_playwright

        seen_ids = self._get_seen_ids()
        discovered_links = []

        if max_vacancies is None:
            max_vacancies = self.config.get("max_vacancies_per_search")

        with sync_playwright() as p:
            mode = "headless (без окна)" if self.headless else "с видимым окном"
            logging.info(f"🔍 Поиск вакансий по запросу «{text}» — режим {mode}")

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=self.headless,
                user_agent=random.choice(self.user_agents),
                proxy=self.proxy,
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
            page = context.new_page()
            page.route("**/*", self._abort_heavy_resources)

            try:
                for current_page in range(page_limit):
                    if len(discovered_links) >= max_vacancies:
                        break

                    search_url = (
                        f"https://hh.ru/search/vacancy?text={text}&search_field=name"
                        f"&area={area}&experience={experience}&search_period={period}"
                        f"&items_on_page=20&page={current_page}"
                    )
                    if schedule:
                        search_url += f"&schedule={schedule}"

                    logging.info(f"📄 Открываю страницу результатов {current_page + 1}/{page_limit}")
                    page.goto(
                        search_url,
                        timeout=self.config.get("browser_timeout_ms"),
                        wait_until="domcontentloaded",
                    )

                    if self._is_captcha_page(page):
                        if self.headless:
                            raise RuntimeError(
                                "hh.ru запросил капчу. В headless-режиме её решить нельзя. "
                                "Отключите 'browser_headless' в настройках и повторите поиск."
                            )
                        logging.warning("⚠️ Капча — решите её вручную в открытом окне браузера...")
                        try:
                            page.wait_for_selector(
                                '[data-qa="vacancy-serp__vacancy"]', timeout=120000
                            )
                            logging.info("✅ Капча решена, продолжаю парсинг...")
                        except Exception:
                            raise RuntimeError(
                                "Таймаут ожидания решения капчи (2 мин). "
                                "Остановите парсинг и попробуйте снова."
                            ) from None

                    self.human_engine.move_mouse_randomly(page)
                    self.human_engine.random_scroll(page)
                    self.human_engine.apply_adaptive_delay(page)

                    soup = BeautifulSoup(page.content(), "html.parser")

                    for link in soup.find_all("a", href=re.compile(r"/vacancy/\d+")):
                        match = re.search(r"/vacancy/(\d+)", link.get("href", ""))
                        if match:
                            v_id = match.group(1)
                            v_name = link.get_text(strip=True)
                            if v_id not in seen_ids and len(v_name) >= 3:
                                if "responses" not in link.get("href", ""):
                                    seen_ids.add(v_id)
                                    discovered_links.append({"id": v_id, "name": v_name})
                                    if len(discovered_links) >= max_vacancies:
                                        break

                total = len(discovered_links)
                logging.info(f"🆕 Найдено новых вакансий: {total}. Начинаю детальный разбор...")

                final_vacancies = []
                for idx, v in enumerate(discovered_links, 1):
                    label = v["name"][:60]
                    logging.info(f"⏳ [{idx}/{total}] Обрабатываю: {label}")
                    if progress_callback:
                        progress_callback(idx, total, label)

                    try:
                        vacancy_info = self._parse_vacancy_detail(page, v["id"], v["name"])
                        if vacancy_info:
                            vd = vacancy_info.to_dict()
                            final_vacancies.append(vd)
                            logging.info(f"✅ [{idx}/{total}] Сохранено: {vacancy_info.company} — {label}")
                            if on_vacancy:
                                on_vacancy(dict(vd))
                    except Exception as e:
                        if self._looks_like_captcha_error(str(e)):
                            logging.warning(f"⚠️ Капча на вакансии {v['id']}. Пауза 30 сек...")
                            time.sleep(30)
                        else:
                            logging.error(f"❌ Ошибка разбора вакансии {v['id']}: {e}")
                        continue

                    time.sleep(random.uniform(2, 5))

                logging.info(f"🏁 Готово. Успешно разобрано: {len(final_vacancies)} из {total}")
                return final_vacancies

            finally:
                context.close()

    def _parse_vacancy_detail(
        self, page: Page, vacancy_id: str, title: str
    ):
        from core.scraper._human import VacancyInfo

        url = f"https://hh.ru/vacancy/{vacancy_id}"
        logging.debug(f"Парсинг карточки: {url}")

        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            logging.warning(f"Не удалось загрузить вакансию {vacancy_id}: {e}")
            return None

        if self._is_captcha_page(page):
            raise Exception(f"Обнаружена капча на странице вакансии {vacancy_id}")

        try:
            page.wait_for_selector(
                "[data-qa='vacancy-title']", timeout=10000, state="attached"
            )
        except Exception:
            logging.debug(f"Заголовок вакансии {vacancy_id} не дождались, парсим как есть")

        self.human_engine.move_mouse_randomly(page)
        self.human_engine.random_scroll(page)
        self.human_engine.apply_adaptive_delay(page)

        soup = BeautifulSoup(page.content(), "html.parser")

        company = self._safe_extract(
            soup,
            lambda s: (
                s.find(attrs={"data-qa": "vacancy-company-name"})
                or s.select_one("[class*='company-name']")
            ),
            default="Не указана",
        )

        description = self._safe_extract(
            soup,
            lambda s: (
                s.find(attrs={"data-qa": "vacancy-description"})
                or s.select_one(".g-user-content")
            ),
            default="Описание отсутствует.",
            separator="\n",
        )

        salary_text = self._safe_extract(
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
            url=url,
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
