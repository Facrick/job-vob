import random
import time
import re
import logging
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page

from core.config import AppConfig
from core.utils import parse_salary_text


@dataclass
class VacancyInfo:
    """DTO для информации о вакансии, полученной парсером."""
    id: str
    title: str
    company: str
    salary_min: Optional[int]
    salary_max: Optional[int]
    description: str
    skills: str
    url: str

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "description": self.description,
            "skills": self.skills,
        }


class HumanInteractionEngine:
    """Эмуляция человеческого поведения для обхода антифрода."""

    def __init__(self, config: AppConfig):
        self.config = config

    def move_mouse_randomly(self, page: Page) -> None:
        try:
            for _ in range(random.randint(2, 4)):
                x = random.randint(150, 1000)
                y = random.randint(150, 700)
                steps = random.randint(
                    self.config.get("human_mouse_steps_min"),
                    self.config.get("human_mouse_steps_max"),
                )
                page.mouse.move(x, y, steps=steps)
        except Exception as e:
            logging.debug(f"[Anti-Fraud] Ошибка движения мыши: {e}")

    def apply_adaptive_delay(self, page: Page) -> None:
        delay = random.randint(
            self.config.get("base_delay_ms_min"),
            self.config.get("base_delay_ms_max"),
        )
        page.wait_for_timeout(delay)

    def random_scroll(self, page: Page) -> None:
        try:
            scroll_y = random.randint(200, 800)
            page.evaluate(f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})")
            page.wait_for_timeout(random.randint(500, 1500))
        except Exception as e:
            logging.debug(f"[Anti-Fraud] Ошибка прокрутки: {e}")


class HHParser:
    """Парсер вакансий с hh.ru с защитой от блокировки."""

    # Узкие фразы, которые встречаются ТОЛЬКО на странице капчи/блокировки.
    # Раньше использовались слова вроде "защита", "verify", "protection" —
    # они часто встречаются в описаниях вакансий (например "защита информации"),
    # из-за чего нормальные вакансии ложно отбраковывались как капча.
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

    def __init__(self, config: Optional[AppConfig] = None, proxy_url: Optional[str] = None):
        # Конфиг можно передать снаружи (переиспользование одного AppConfig
        # на всё приложение), либо создаётся свой.
        self.config = config or AppConfig()
        self.human_engine = HumanInteractionEngine(self.config)
        self.proxy = {"server": proxy_url} if proxy_url else None
        self.user_data_dir = Path("data/browser_user_data")
        self.user_data_dir.mkdir(parents=True, exist_ok=True)

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/125.0",
        ]

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
        """Определяет страницу капчи/блокировки по надёжным признакам.

        Проверяет (в порядке дешевизны):
        1. URL — hh.ru редиректит на /captcha при блокировке;
        2. наличие реального DOM-элемента капчи;
        3. заголовок страницы на узкие фразы.

        НЕ ищет слова в теле страницы — это давало ложные срабатывания
        на вакансиях со словами "защита", "verify", "security" в описании.
        """
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
        progress_callback: Optional[Callable] = None,
        max_vacancies: Optional[int] = None,
    ) -> List[Dict]:
        seen_ids = self._get_seen_ids()
        discovered_links = []

        if max_vacancies is None:
            max_vacancies = self.config.get("max_vacancies_per_search")

        with sync_playwright() as p:
            logging.info(f"[Playwright] Запуск поиска по запросу: {text}")

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=False,
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

                    logging.info(f"Загрузка страницы {current_page + 1}/{page_limit}")
                    page.goto(
                        search_url,
                        timeout=self.config.get("browser_timeout_ms"),
                        wait_until="domcontentloaded",
                    )

                    if self._is_captcha_page(page):
                        logging.warning("⚠️ ОБНАРУЖЕНА КАПЧА! Решите её вручную в открытом окне браузера.")
                        try:
                            page.wait_for_selector(
                                '[data-qa="vacancy-serp__vacancy"]', timeout=120000
                            )
                            logging.info("✅ Капча решена, продолжаем парсинг...")
                        except Exception:
                            raise Exception(
                                "Таймаут ожидания решения капчи (2 мин). "
                                "Остановите парсинг и попробуйте снова."
                            )

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

                logging.info(f"Найдено {len(discovered_links)} новых вакансий")

                final_vacancies = []
                for idx, v in enumerate(discovered_links, 1):
                    if progress_callback:
                        progress_callback(idx, len(discovered_links))

                    try:
                        vacancy_info = self._parse_vacancy_detail(page, v["id"], v["name"])
                        if vacancy_info:
                            final_vacancies.append(vacancy_info.to_dict())
                    except Exception as e:
                        if self._looks_like_captcha_error(str(e)):
                            logging.warning(f"⚠️ Капча на вакансии {v['id']}. Пауза 30 сек...")
                            time.sleep(30)
                        else:
                            logging.error(f"Ошибка парсинга вакансии {v['id']}: {e}")
                        continue

                    time.sleep(random.uniform(2, 5))

                return final_vacancies

            finally:
                context.close()

    def _parse_vacancy_detail(
        self, page: Page, vacancy_id: str, title: str
    ) -> Optional[VacancyInfo]:
        url = f"https://hh.ru/vacancy/{vacancy_id}"
        logging.debug(f"Парсинг карточки: {url}")

        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
        except Exception as e:
            logging.warning(f"Не удалось загрузить вакансию {vacancy_id}: {e}")
            return None

        # Капча — единственный случай, который пробрасываем наверх (для паузы)
        if self._is_captcha_page(page):
            raise Exception(f"Обнаружена капча на странице вакансии {vacancy_id}")

        # Ждём появления заголовка вакансии — значит контент прогрузился.
        # Если не дождались, всё равно пытаемся распарсить что есть.
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

        # Каждое поле извлекается изолированно: сбой одного не теряет остальные.
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
        """Безопасно извлекает текст из тега, найденного finder(soup).

        Любой сбой -> возвращается default, а не исключение. Это убирает
        ложные «ошибки парсинга», когда у вакансии просто нет какого-то блока.
        """
        try:
            tag = finder(soup)
            if not tag:
                return default
            if separator:
                return tag.get_text(separator=separator, strip=True)
            return tag.get_text(strip=True)
        except Exception:
            return default

    def auto_apply(self, vacancy_id: str, letter_text: str) -> Tuple[bool, str]:
        with sync_playwright() as p:
            logging.info(f"[Auto-Apply] Отклик на вакансию {vacancy_id}")

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=False,
                user_agent=random.choice(self.user_agents),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            try:
                page.goto(
                    f"https://hh.ru/vacancy/{vacancy_id}",
                    timeout=40000,
                    wait_until="domcontentloaded",
                )

                apply_btn = page.locator('a[data-qa="vacancy-response-link-top"]').first
                if not apply_btn.is_visible():
                    return False, "Кнопка 'Откликнуться' не найдена. Возможно, отклик уже отправлен."

                apply_btn.click()
                page.wait_for_timeout(2000)

                letter_toggle = page.locator('button[data-qa="vacancy-response-letter-toggle"]')
                if letter_toggle.is_visible():
                    letter_toggle.click()
                    page.wait_for_timeout(1000)

                letter_textarea = page.locator(
                    'textarea[data-qa="vacancy-response-popup-form-letter-input"]'
                )
                if letter_textarea.is_visible():
                    letter_textarea.fill(letter_text[:3000])
                    page.wait_for_timeout(1500)

                submit_btn = page.locator('button[data-qa="vacancy-response-submit-popup"]')
                if submit_btn.is_visible():
                    submit_btn.click()
                    page.wait_for_timeout(3000)
                    return True, "Автоотклик успешно отправлен!"

                return False, "Не удалось найти кнопку подтверждения отправки."

            except Exception as e:
                logging.error(f"[Auto-Apply] Ошибка: {e}")
                return False, f"Сбой автоматизации: {str(e)}"
            finally:
                context.close()
