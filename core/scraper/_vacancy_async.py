"""Асинхронный парсинг вакансий с hh.ru — миксин для HHParser.

Зеркалит sync-метод parse_market из _vacancy.py, но на playwright.async_api.
Главное отличие и причина существования — детальный разбор карточек идёт
ПАРАЛЛЕЛЬНО в нескольких вкладках (asyncio.Semaphore), что и даёт ускорение.

Капча/vpncheck-логика и анти-фрод задержки переиспользуют sync-хелперы из
_VacancyMixin там, где это безопасно (проверки по page.url синхронны в async
тоже не блокируют — но реальные обращения к DOM здесь сделаны через await).
"""
import asyncio
import logging
import random
import re
from collections.abc import Callable
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from core.scraper._constants import (
    HH_BASE_URL,
    HH_VACANCY_URL,
    TIMEOUT_PAGE_LOAD_MS,
    TIMEOUT_SELECTOR_MS,
)

# Сколько вкладок Chromium разбирать параллельно по умолчанию. Переопределяется
# из config (search_concurrency). Выше → быстрее, но больше нагрузка/риск капчи.
DEFAULT_CONCURRENCY = 6


class _SearchCancelled(Exception):
    """Внутренний сигнал: пользователь нажал «Стоп» во время ожидания/поиска."""


def _as_list(value) -> list[str]:
    """Нормализует фильтр (None / строка / список) в список непустых строк.

    Нужно для experience/schedule, которые из GUI приходят списком (multiple),
    но из тестов/старого кода могут прийти строкой.
    """
    if not value:
        return []
    if isinstance(value, str):
        return [value]
    return [str(v) for v in value if v]


class _VacancyAsyncMixin:
    """Async-вариант поиска вакансий с параллельным детальным разбором."""

    async def parse_market_async(
        self,
        text: str = "",
        period: int = 1,
        area: int = 113,
        experience: str | list[str] = "between1And3",
        schedule: str | list[str] = "",
        search_field: str = "name,company_name,description",
        page_limit: int = 1,
        progress_callback: Callable | None = None,
        max_vacancies: int | None = None,
        on_vacancy: Callable | None = None,
        should_cancel: Callable[[], bool] | None = None,
        headless: bool | None = None,
        concurrency: int = DEFAULT_CONCURRENCY,
    ) -> list[dict]:
        from playwright.async_api import async_playwright

        def _cancelled() -> bool:
            return bool(should_cancel and should_cancel())

        if headless is None:
            headless = self.headless
        if not max_vacancies:
            max_vacancies = 200
        effective_page_limit = page_limit if page_limit > 0 else 50

        seen_ids: set = set()
        discovered_links: list[dict] = []

        async with async_playwright() as p:
            mode = "headless (без окна)" if headless else "с видимым окном"
            logging.info(f"🔍 [async] Поиск вакансий по запросу «{text}» — режим {mode}")

            context = await self._launch_context_async(p, headless=headless)
            try:
                page = await context.new_page()
                await page.route("**/*", self._abort_heavy_resources_async)

                # ── Сбор ссылок (последовательно по страницам выдачи) ──────────
                for current_page in range(effective_page_limit):
                    if _cancelled():
                        logging.info("🛑 Сбор ссылок остановлен пользователем.")
                        break
                    if len(discovered_links) >= max_vacancies:
                        break

                    search_url = (
                        f"{HH_BASE_URL}/search/vacancy?text={quote_plus(text)}"
                        f"&search_field={quote_plus(search_field)}"
                        f"&area={area}&search_period={period}"
                        f"&items_on_page=20&page={current_page}"
                    )
                    # experience/schedule могут быть списком (несколько грейдов /
                    # форматов) → hh.ru принимает повторяющиеся параметры.
                    for exp_val in _as_list(experience):
                        search_url += f"&experience={exp_val}"
                    for sched_val in _as_list(schedule):
                        search_url += f"&schedule={sched_val}"
                    logging.info(f"🌐 GET {search_url}")

                    logging.info(
                        f"📄 Открываю страницу результатов {current_page + 1}/{page_limit}"
                    )
                    await page.goto(
                        search_url,
                        timeout=self.config.get("browser_timeout_ms"),
                        wait_until="domcontentloaded",
                    )

                    if await self._is_blocked_page_async(page):
                        # Разблокировку (капча/vpncheck) проходит человек в видимом
                        # окне. Ждём опросом — кнопка «Стоп» прерывает ожидание.
                        try:
                            await self._wait_for_unblock_async(
                                page, search_url,
                                should_cancel=should_cancel, headless=headless,
                            )
                        except _SearchCancelled:
                            logging.info("🛑 Поиск остановлен во время проверки hh.ru.")
                            break

                    try:
                        await page.wait_for_selector(
                            "a[href*='/vacancy/']", timeout=15000, state="attached"
                        )
                    except Exception:
                        logging.warning(
                            "⚠️ Карточки вакансий не появились за 15 сек — парсим как есть"
                        )

                    html = await page.content()
                    soup = BeautifulSoup(html, "html.parser")
                    links_found = soup.find_all("a", href=re.compile(r"/vacancy/\d+"))
                    logging.info(
                        f"🔗 Найдено ссылок на вакансии на странице: {len(links_found)}"
                    )

                    new_on_page = 0
                    for link in links_found:
                        match = re.search(r"/vacancy/(\d+)", link.get("href", ""))
                        if not match:
                            continue
                        v_id = match.group(1)
                        v_name = link.get_text(strip=True)
                        if (
                            v_id not in seen_ids
                            and len(v_name) >= 3
                            and "responses" not in link.get("href", "")
                        ):
                            seen_ids.add(v_id)
                            discovered_links.append({"id": v_id, "name": v_name})
                            new_on_page += 1
                            if len(discovered_links) >= max_vacancies:
                                break

                    if new_on_page == 0:
                        logging.info(
                            "📭 Новых вакансий на странице нет — завершаю постраничный обход."
                        )
                        break

                total = len(discovered_links)
                logging.info(
                    f"🆕 Найдено новых вакансий: {total}. "
                    f"Параллельный разбор по {concurrency} вкладкам..."
                )

                # ── Детальный разбор (параллельно, под семафором) ──────────────
                final_vacancies: list[dict] = []
                sem = asyncio.Semaphore(max(1, concurrency))
                lock = asyncio.Lock()
                done = 0

                async def _worker(v: dict) -> None:
                    nonlocal done
                    if _cancelled():
                        return
                    async with sem:
                        if _cancelled():
                            return
                        detail_page = await context.new_page()
                        await detail_page.route("**/*", self._abort_heavy_resources_async)
                        try:
                            vd = await self._parse_vacancy_detail_async(
                                detail_page, v["id"], v["name"]
                            )
                        except Exception as e:
                            if self._looks_like_captcha_error(str(e)):
                                logging.warning(
                                    f"⚠️ Капча на вакансии {v['id']}. Пропускаю."
                                )
                            else:
                                logging.error(
                                    f"❌ Ошибка разбора вакансии {v['id']}: {e}"
                                )
                            vd = None
                        finally:
                            await detail_page.close()
                    # Колбэки и общий список — под локом (event loop один, но
                    # держим инвариант явно и считаем прогресс детерминированно).
                    async with lock:
                        done += 1
                        label = v["name"][:60]
                        if progress_callback:
                            progress_callback(done, total, label)
                        if vd is not None:
                            final_vacancies.append(vd)
                            logging.info(
                                f"✅ [{done}/{total}] Сохранено: "
                                f"{vd.get('company')} — {label}"
                            )
                            if on_vacancy:
                                on_vacancy(dict(vd))

                await asyncio.gather(*(_worker(v) for v in discovered_links))

                logging.info(
                    f"🏁 Готово. Успешно разобрано: {len(final_vacancies)} из {total}"
                )
                return final_vacancies
            finally:
                await context.close()

    async def _abort_heavy_resources_async(self, route) -> None:
        url = route.request.url.lower()
        blocked_keywords = [
            "metrika", "google-analytics", "analytics",
            "adv", "banner", "doubleclick", "facebook",
            "tracking", "pixel", "hotjar",
        ]
        if any(keyword in url for keyword in blocked_keywords):
            await route.abort()
        else:
            await route.continue_()

    async def _is_blocked_page_async(self, page) -> bool:
        try:
            url = page.url.lower()
            if any(m in url for m in self.VPNCHECK_URL_MARKERS):
                return True
            if any(m in url for m in self.CAPTCHA_URL_MARKERS):
                return True
            for selector in self.CAPTCHA_SELECTORS:
                try:
                    if await page.locator(selector).count() > 0:
                        return True
                except Exception:
                    continue
            title = (await page.title()).lower()
            if any(m in title for m in self.CAPTCHA_TITLE_MARKERS):
                return True
        except Exception:
            return False
        return False

    async def _wait_for_unblock_async(
        self, page, target_url: str, *,
        timeout_ms: int = 180_000,
        should_cancel: Callable[[], bool] | None = None,
        headless: bool = False,
    ) -> None:
        """Ждёт прохождения капчи/vpncheck, опрашивая состояние короткими шагами.

        В отличие от единого wait_for_function на 3 минуты, проверяет should_cancel
        каждую секунду — поэтому кнопка «Стоп» срабатывает сразу, а не зависает.
        В headless-режиме пройти проверку человеку негде → сразу понятная ошибка.
        """
        if headless:
            raise RuntimeError(
                "hh.ru заблокировал запрос (VPN/капча), а браузер работает в "
                "фоновом режиме — пройти проверку негде. Включите «Показывать "
                "браузер» и повторите поиск."
            )

        logging.warning(
            "⚠️  hh.ru заблокировал запрос (VPN/капча). "
            "Пройдите проверку в открытом окне браузера — "
            f"у вас {timeout_ms // 1000} секунд."
        )

        deadline = timeout_ms
        elapsed = 0
        step = 1000  # шаг опроса, мс
        while elapsed < deadline:
            if should_cancel and should_cancel():
                raise _SearchCancelled()
            # Проверка пройдена, когда URL ушёл со страницы vpncheck/captcha.
            if not await self._is_blocked_page_async(page):
                logging.info("✅ Проверка пройдена, продолжаю…")
                await page.wait_for_timeout(2000)
                await page.goto(target_url, wait_until="domcontentloaded")
                return
            await page.wait_for_timeout(step)
            elapsed += step

        raise RuntimeError(
            f"Таймаут ожидания прохождения проверки hh.ru ({timeout_ms // 1000} с). "
            "Попробуйте снова."
        )

    async def _parse_vacancy_detail_async(self, page, vacancy_id: str, title: str):
        url = HH_VACANCY_URL.format(vacancy_id=vacancy_id)
        try:
            await page.goto(url, timeout=TIMEOUT_PAGE_LOAD_MS, wait_until="domcontentloaded")
        except Exception as e:
            logging.warning(f"Не удалось загрузить вакансию {vacancy_id}: {e}")
            return None

        if await self._is_blocked_page_async(page):
            raise Exception(f"Обнаружена капча на странице вакансии {vacancy_id}")

        try:
            await page.wait_for_selector(
                "[data-qa='vacancy-title']", timeout=TIMEOUT_SELECTOR_MS, state="attached"
            )
        except Exception:
            logging.debug(f"Заголовок вакансии {vacancy_id} не дождались, парсим как есть")

        html = await page.content()
        info = self._build_vacancy_info(html, vacancy_id, title)
        return info.to_dict() if info else None
