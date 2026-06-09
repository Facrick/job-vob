import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from bs4 import BeautifulSoup
from playwright.sync_api import Page, sync_playwright

from core.config import AppConfig
from core.paths import user_path
from core.utils import parse_salary_text


@dataclass
class VacancyInfo:
    """DTO для информации о вакансии, полученной парсером."""
    id: str
    title: str
    company: str
    salary_min: int | None
    salary_max: int | None
    description: str
    skills: str
    url: str

    def to_dict(self) -> dict:
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

    def __init__(self, config: AppConfig | None = None, proxy_url: str | None = None):
        # Конфиг можно передать снаружи (переиспользование одного AppConfig
        # на всё приложение), либо создаётся свой.
        self.config = config or AppConfig()
        self.human_engine = HumanInteractionEngine(self.config)
        self.proxy = {"server": proxy_url} if proxy_url else None
        # Headless по умолчанию: анализ вакансий идёт без видимого окна Chrome.
        self.headless = bool(self.config.get("browser_headless"))
        self.user_data_dir = user_path("data/browser_user_data")

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
        progress_callback: Callable | None = None,
        max_vacancies: int | None = None,
        on_vacancy: Callable | None = None,
    ) -> list[dict]:
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
                            # В headless нет окна, где решить капчу — останавливаемся понятно.
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
    ) -> VacancyInfo | None:
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
        with sync_playwright() as p:
            return self._check_logged_in(p)

    # ── Синхронизация переговоров ─────────────────────────────────────────────

    # Ключевые слова для определения статуса из текста страницы вакансии.
    # Ищем в зоне отклика/статуса — порядок важен (специфичные первыми).
    _RESP_STATUS_KEYWORDS = [
        "оффер", "предложение о работе",
        "приглашение", "приглашен", "телефонное интервью", "интервью", "собеседование",
        "отказ", "отклонен", "не подошл",
        "просмотрен",
        "отклик отправлен", "вы уже откликнулись", "отклик рассматривается",
    ]

    def fetch_negotiations(
        self,
        vacancy_ids: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[dict]:
        """Проверяет статус откликов по прямым ссылкам на вакансии из CRM.

        Принимает список vacancy_id из БД, заходит на каждую страницу
        https://hh.ru/vacancy/{id} и читает текущий статус отклика.
        Это надёжнее парсинга списка переговоров — DOM конкретной вакансии
        стабильнее и мы точно знаем какие ID проверять.

        Возвращает список {vacancy_id, hh_status, title, company}.
        Поднимает RuntimeError если не авторизован.
        """
        if not vacancy_ids:
            return []

        with sync_playwright() as p:
            if not self._check_logged_in(p):
                raise RuntimeError(
                    "Не авторизован на hh.ru. "
                    "Войдите через кнопку «Войти» и повторите синхронизацию."
                )

            ctx = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=True,
                user_agent=random.choice(self.user_agents),
                viewport={"width": 1280, "height": 800},
            )
            try:
                page = ctx.new_page()
                results: list[dict] = []
                total = len(vacancy_ids)

                for idx, vid in enumerate(vacancy_ids, 1):
                    url = f"https://hh.ru/vacancy/{vid}"
                    logging.info(f"[Sync] {idx}/{total} → {url}")
                    if progress_callback:
                        progress_callback(idx, total, f"{idx}/{total}: вакансия {vid}")

                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(1200)
                        html = page.content()
                        item = self._check_vacancy_response_html(html, vid)
                        results.append(item)
                        logging.info(
                            f"[Sync] {vid}: статус = «{item['hh_status'] or 'не определён'}»"
                        )
                    except Exception as exc:
                        logging.warning(f"[Sync] Ошибка при проверке {vid}: {exc}")
                        results.append({
                            "vacancy_id": vid,
                            "hh_status": "",
                            "title": "",
                            "company": "",
                        })

                return results
            finally:
                ctx.close()

    def _check_vacancy_response_html(self, html: str, vacancy_id: str) -> dict:
        """Извлекает статус отклика из HTML страницы вакансии.

        hh.ru показывает статус в блоке рядом с кнопкой «Откликнуться»:
        - data-qa="vacancy-response-status" / "response-status"
        - Текст «Приглашение», «Отказ», «Отклик отправлен» и т.п.
        Если вакансия закрыта/удалена — статус помечается как «закрыта».
        """
        soup = BeautifulSoup(html, "html.parser")

        title = ""
        h1 = soup.find("h1", {"data-qa": re.compile(r"vacancy-title|vacancy-name", re.I)})
        if not h1:
            h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

        company = ""
        for attrs in [
            {"data-qa": re.compile(r"vacancy-company-name|employer-name", re.I)},
            {"class": re.compile(r"vacancy-company-name|employer-name", re.I)},
        ]:
            tag = soup.find(attrs=attrs)
            if tag:
                company = tag.get_text(strip=True)
                break

        # Проверяем не закрыта ли вакансия
        page_text = soup.get_text(" ", strip=True).lower()
        if any(m in page_text for m in ("вакансия не найдена", "вакансия удалена",
                                         "вакансия скрыта", "vacancy not found")):
            return {"vacancy_id": vacancy_id, "hh_status": "закрыта",
                    "title": title, "company": company}

        # Ищем зону статуса отклика — сначала по data-qa, потом по ключевым словам
        status_text = ""

        # 1. Целевые data-qa элементы для статуса отклика
        for dqa in [
            "vacancy-response-status", "response-status",
            "negotiations-status", "negotiation-status",
        ]:
            tag = soup.find(attrs={"data-qa": re.compile(dqa, re.I)})
            if tag:
                status_text = tag.get_text(strip=True).lower()
                if status_text:
                    break

        # 2. Блок рядом с кнопкой отклика — ищем зону apply-кнопки и читаем текст
        if not status_text:
            for dqa in [
                "vacancy-response-link-top", "vacancy-response-link-bottom",
                "vacancy-response", "apply-block",
            ]:
                zone = soup.find(attrs={"data-qa": re.compile(dqa, re.I)})
                if not zone:
                    continue
                # Идём на 2 уровня вверх — там обычно статус рядом с кнопкой
                parent = zone.parent
                if parent and parent.parent:
                    parent = parent.parent
                zone_text = parent.get_text(" ", strip=True).lower() if parent else ""
                for keyword in self._RESP_STATUS_KEYWORDS:
                    if keyword in zone_text:
                        status_text = keyword
                        break
                if status_text:
                    break

        # 3. Ищем ключевые слова по всей странице (менее точно, но работает)
        if not status_text:
            for keyword in self._RESP_STATUS_KEYWORDS:
                if keyword in page_text:
                    status_text = keyword
                    break

        return {
            "vacancy_id": vacancy_id,
            "hh_status": status_text,
            "title": title,
            "company": company,
        }

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
            # Ждём, пока URL сменится с login-страницы — надёжнее DOM-селекторов
            pg.wait_for_url(
                lambda url: "/account/login" not in url,
                timeout=180_000,
            )
            # Небольшая пауза, чтобы сессия записалась на диск
            pg.wait_for_timeout(2000)
            logging.info("✅ Авторизация выполнена. Закрываю окно и продолжаю в фоне...")
            return True
        except Exception as e:
            logging.warning(f"⚠️ Авторизация не завершена: {e}")
            return False
        finally:
            ctx.close()

    def auto_apply(self, vacancy_id: str, letter_text: str) -> tuple[bool, str]:
        with sync_playwright() as p:
            logging.info(f"📨 Отправляю отклик на вакансию {vacancy_id}...")

            # Проверяем авторизацию; если нет — просим войти через браузер
            if not self._check_logged_in(p):
                logging.info("🔒 Сессия hh.ru не найдена — требуется авторизация.")
                if not self._login_in_browser(p):
                    return False, (
                        "Авторизация на hh.ru не выполнена. "
                        "Повторите попытку и войдите в аккаунт в открывшемся окне браузера."
                    )

            # После авторизации отклик всегда отправляем в headless-режиме
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(self.user_data_dir),
                headless=True,
                user_agent=random.choice(self.user_agents),
                viewport={"width": 1280, "height": 800},
            )
            page = context.new_page()

            def first_visible(selectors, timeout_ms=5000):
                """Первый видимый элемент из списка селекторов (с ожиданием)."""
                deadline = time.time() + timeout_ms / 1000
                while time.time() < deadline:
                    for sel in selectors:
                        loc = page.locator(sel).first
                        try:
                            if loc.count() and loc.is_visible():
                                return loc
                        except Exception:
                            continue
                    page.wait_for_timeout(250)
                return None

            try:
                page.goto(
                    f"https://hh.ru/vacancy/{vacancy_id}",
                    timeout=40000,
                    wait_until="domcontentloaded",
                )
                # Небольшая пауза: hh.ru может подгружать кнопку динамически
                page.wait_for_timeout(2000)

                apply_btn = first_visible([
                    # data-qa атрибуты (основные)
                    '[data-qa="vacancy-response-link-top"]',
                    '[data-qa="vacancy-response-link-bottom"]',
                    # По тексту кнопки (резервный вариант)
                    'button:has-text("Откликнуться")',
                    'a:has-text("Откликнуться")',
                    # Широкий поиск по частичному тексту
                    ':text("Откликнуться")',
                ], timeout_ms=15000)
                if not apply_btn:
                    return False, ("Кнопка «Откликнуться» не найдена. Вероятные причины: "
                                   "отклик уже отправлен ранее, вакансия закрыта, "
                                   "или требуется повторная авторизация на hh.ru.")

                logging.info("🖱 Нажимаю «Откликнуться»...")
                apply_btn.click()
                page.wait_for_timeout(2500)

                # Раскрываем поле письма, если оно скрыто за тоглом/ссылкой
                toggle = first_visible([
                    '[data-qa="vacancy-response-letter-toggle"]',
                    'button:has-text("Сопроводительное письмо")',
                    'text=Добавить сопроводительное',
                ], timeout_ms=2500)
                if toggle:
                    logging.info("✉️ Раскрываю поле сопроводительного письма...")
                    toggle.click()
                    page.wait_for_timeout(1000)

                # Поле письма ОБЯЗАТЕЛЬНО: без него отклик не отправляем.
                textarea = first_visible([
                    'textarea[data-qa="vacancy-response-popup-form-letter-input"]',
                    'textarea[data-qa="vacancy-response-letter-input"]',
                    'textarea[name="text"]',
                    '.vacancy-response-popup textarea',
                ], timeout_ms=6000)
                if not textarea:
                    logging.error("❌ Поле письма не найдено — отклик НЕ отправлен.")
                    return False, ("Не удалось прикрепить сопроводительное письмо: поле ввода "
                                   "не найдено. Отклик не отправлен (чтобы не уйти без письма).")

                logging.info("⌨️ Вставляю текст сопроводительного письма...")
                textarea.fill(letter_text[:3000])
                page.wait_for_timeout(1000)
                if not (textarea.input_value() or "").strip():
                    return False, "Письмо не вставилось в поле. Отклик не отправлен."

                submit_btn = first_visible([
                    'button[data-qa="vacancy-response-submit-popup"]',
                    '[data-qa="vacancy-response-letter-submit"]',
                    'button[data-qa="vacancy-response-submit"]',
                    '.vacancy-response-popup button[type="submit"]',
                ], timeout_ms=4000)
                if not submit_btn:
                    return False, "Не найдена кнопка отправки отклика."

                logging.info("📤 Отправляю отклик вместе с письмом...")
                submit_btn.click()
                page.wait_for_timeout(3000)
                return True, "Автоотклик с сопроводительным письмом отправлен!"

            except Exception as e:
                logging.error(f"[Auto-Apply] Ошибка: {e}")
                return False, f"Сбой автоматизации: {str(e)}"
            finally:
                context.close()
