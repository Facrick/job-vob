"""Сбор зарплатных ожиданий соискателей с hh.ru/search/resume."""
import asyncio
import logging
import re
import statistics
from collections.abc import Callable
from urllib.parse import quote_plus

from core.scraper._constants import (
    HH_BASE_URL,
    TIMEOUT_PAGE_LOAD_MS,
    TIMEOUT_SELECTOR_MS,
)


class _ResumeStatsMixin:
    """Парсинг зарплатных ожиданий соискателей со страницы поиска резюме."""

    _RESUME_SEARCH_URL = HH_BASE_URL + "/search/resume"

    def collect_salary_stats(
        self,
        query: str,
        area: int = 113,
        max_pages: int = 5,
        concurrency: int = 3,
        progress_callback: Callable[[str, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict:
        """Собирает зарплатные ожидания соискателей — запускает async в новом loop."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self._collect_salary_stats_async(
                    query=query,
                    area=area,
                    max_pages=max_pages,
                    concurrency=concurrency,
                    progress_callback=progress_callback,
                    should_cancel=should_cancel,
                )
            )
        finally:
            loop.close()

    async def _collect_salary_stats_async(
        self,
        query: str,
        area: int = 113,
        max_pages: int = 5,
        concurrency: int = 3,
        progress_callback: Callable[[str, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict:
        from playwright.async_api import async_playwright

        def _report(msg: str, pct: int = 0):
            logging.info(msg)
            if progress_callback:
                progress_callback(msg, pct)

        def _cancelled() -> bool:
            return bool(should_cancel and should_cancel())

        def _make_url(page_num: int) -> str:
            # Параметры logic=normal и pos=full_text обязательны: без них hh.ru
            # не применяет текстовый фильтр к выдаче резюме и отдаёт одну и ту же
            # ленту для любого запроса. Повторяем набор, который сайт ставит сам.
            return (
                f"{self._RESUME_SEARCH_URL}"
                f"?text={quote_plus(query)}"
                f"&area={area}"
                f"&isDefaultArea=true"
                f"&ored_clusters=true"
                f"&order_by=relevance"
                f"&search_period=0"
                f"&logic=normal"
                f"&pos=full_text"
                f"&exp_period=all_time"
                f"&items_on_page=20"
                f"&page={page_num}"
            )

        salaries: list[int] = []

        async with async_playwright() as p:
            context = await self._launch_context_async(p, headless=self.headless)
            try:
                # ── Шаг 1: первая страница — узнаём total_pages ──────────────
                logging.info(f"[salary] сбор для query={query!r} url={_make_url(0)}")
                _report("📄 Определяем количество страниц…", 2)
                first_page = await context.new_page()
                await first_page.route("**/*", self._abort_heavy_resources_async)
                await first_page.goto(
                    _make_url(0), wait_until="domcontentloaded", timeout=TIMEOUT_PAGE_LOAD_MS
                )

                if await self._is_blocked_page_async(first_page):
                    _report("⚠️ hh.ru заблокировал — попробуйте позже.", 0)
                    await first_page.close()
                    return self._build_stats(query, [])

                total_pages = await self._parse_resume_page_count_async(first_page) or 1
                pages_to_fetch = min(total_pages, max_pages)

                first_salaries = await self._parse_resume_salaries_async(first_page)
                salaries.extend(first_salaries)
                await first_page.close()
                _report(f"✅ Стр. 1/{pages_to_fetch}: {len(first_salaries)} з/п", 10)

                if _cancelled() or pages_to_fetch <= 1:
                    return self._build_stats(query, salaries)

                # ── Шаг 2: батчи по concurrency страниц, стоп между батчами ─
                async def _fetch_page(page_num: int) -> list[int]:
                    pg = await context.new_page()
                    await pg.route("**/*", self._abort_heavy_resources_async)
                    try:
                        await pg.goto(
                            _make_url(page_num),
                            wait_until="domcontentloaded",
                            timeout=TIMEOUT_PAGE_LOAD_MS,
                        )
                        if await self._is_blocked_page_async(pg):
                            logging.warning(f"[salary] стр.{page_num+1} заблокирована")
                            return []
                        return await self._parse_resume_salaries_async(pg)
                    except Exception as e:
                        logging.warning(f"[salary] ошибка стр.{page_num+1}: {e}")
                        return []
                    finally:
                        await pg.close()

                remaining = list(range(1, pages_to_fetch))
                done = 1
                while remaining:
                    if _cancelled():
                        _report("🛑 Сбор остановлен.", 0)
                        break
                    batch = remaining[:concurrency]
                    remaining = remaining[concurrency:]
                    results = await asyncio.gather(*(_fetch_page(i) for i in batch))
                    for r in results:
                        salaries.extend(r)
                    done += len(batch)
                    pct = int(done / pages_to_fetch * 90)
                    _report(f"✅ Обработано {done}/{pages_to_fetch} стр., з/п: {len(salaries)}", pct)

            finally:
                await context.close()

        _report(f"🏁 Готово: {len(salaries)} резюме с указанной з/п", 100)
        return self._build_stats(query, salaries)

    def _parse_resume_page_count(self, page) -> int:
        """Парсит общее число страниц пагинации (sync)."""
        try:
            pager = page.locator('[data-qa="pager-page"]').all()
            if pager:
                nums = []
                for el in pager:
                    try:
                        nums.append(int(el.inner_text().strip()))
                    except ValueError:
                        pass
                return max(nums) if nums else 1
            text = page.locator('[data-qa="pager-block"]').first.inner_text(timeout=3000)
            m = re.search(r"(\d+)\s*$", text)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return 1

    async def _parse_resume_page_count_async(self, page) -> int:
        """Парсит общее число страниц пагинации (async)."""
        try:
            pager = await page.locator('[data-qa="pager-page"]').all()
            if pager:
                nums = []
                for el in pager:
                    try:
                        nums.append(int((await el.inner_text()).strip()))
                    except ValueError:
                        pass
                return max(nums) if nums else 1
            text = await page.locator('[data-qa="pager-block"]').first.inner_text(timeout=3000)
            m = re.search(r"(\d+)\s*$", text)
            if m:
                return int(m.group(1))
        except Exception:
            pass
        return 1

    def _parse_resume_salaries(self, page) -> list[int]:
        """Парсит зарплатные ожидания из карточек (sync, для первой страницы)."""
        salaries = []
        try:
            page.wait_for_selector(
                '[data-qa="resume-serp__resume"], .resume-search-item',
                timeout=TIMEOUT_SELECTOR_MS,
            )
        except Exception:
            logging.warning("[salary] Карточки резюме не найдены")
            return salaries

        cards = page.locator('[data-qa="resume-serp__resume"]').all()
        if not cards:
            cards = page.locator('.resume-search-item').all()

        logging.info(f"[salary] Найдено карточек: {len(cards)}")
        for card in cards:
            salary = self._extract_salary_from_card(card)
            if salary:
                salaries.append(salary)

        if not salaries and cards:
            try:
                sample = cards[0].inner_html(timeout=3000)
                logging.debug(f"[salary] HTML первой карточки:\n{sample[:2000]}")
                logging.warning("[salary] Зарплаты не найдены — возможно hh.ru изменил вёрстку")
            except Exception:
                pass
        return salaries

    async def _parse_resume_salaries_async(self, page) -> list[int]:
        """Async-версия парсинга зарплат для параллельных страниц."""
        salaries = []
        try:
            await page.wait_for_selector(
                '[data-qa="resume-serp__resume"], .resume-search-item',
                timeout=TIMEOUT_SELECTOR_MS,
            )
        except Exception:
            logging.warning("[salary] Карточки резюме не найдены")
            return salaries

        cards = await page.locator('[data-qa="resume-serp__resume"]').all()
        if not cards:
            cards = await page.locator('.resume-search-item').all()

        logging.info(f"[salary] Найдено карточек: {len(cards)}")
        for card in cards:
            salary = await self._extract_salary_from_card_async(card)
            if salary:
                salaries.append(salary)

        if not salaries and cards:
            try:
                sample = await cards[0].inner_html(timeout=3000)
                logging.debug(f"[salary] HTML первой карточки:\n{sample[:2000]}")
                logging.warning("[salary] Зарплаты не найдены — возможно hh.ru изменил вёрстку")
            except Exception:
                pass
        return salaries

    def _extract_salary_from_card(self, card) -> int | None:
        """Sync-версия: извлекает зарплату из карточки резюме."""
        selectors = [
            '[class*="magritte-text_typography-subtitle-2-semibold"]',
            '[data-qa="resume-serp__resume-compensation"]',
            '[data-qa*="compensation"]',
            '.compensation',
            '.resume-search-item__compensation',
        ]
        for sel in selectors:
            try:
                el = card.locator(sel).first
                if el.count() == 0:
                    continue
                text = el.inner_text(timeout=2000).strip()
                if text and any(c in text for c in ("₽", "руб")):
                    return _parse_salary_value(text)
            except Exception:
                continue
        return None

    async def _extract_salary_from_card_async(self, card) -> int | None:
        """Async-версия: извлекает зарплату из карточки резюме."""
        selectors = [
            '[class*="magritte-text_typography-subtitle-2-semibold"]',
            '[data-qa="resume-serp__resume-compensation"]',
            '[data-qa*="compensation"]',
            '.compensation',
            '.resume-search-item__compensation',
        ]
        for sel in selectors:
            try:
                el = card.locator(sel).first
                if await el.count() == 0:
                    continue
                text = (await el.inner_text(timeout=2000)).strip()
                if text and any(c in text for c in ("₽", "руб")):
                    val = _parse_salary_value(text)
                    logging.debug(f"[salary] parsed: {text!r} → {val}")
                    return val
            except Exception:
                continue
        return None

    def _build_stats(self, query: str, salaries: list[int]) -> dict:
        """Строит агрегированную статистику из списка зарплат."""
        if not salaries:
            return {
                "query": query,
                "count": 0,
                "median": 0,
                "mean": 0,
                "min": 0,
                "max": 0,
                "distribution": [],
            }

        salaries_sorted = sorted(salaries)
        median_val = int(statistics.median(salaries_sorted))
        mean_val = int(sum(salaries_sorted) / len(salaries_sorted))
        min_val = salaries_sorted[0]
        max_val = salaries_sorted[-1]

        # Гистограмма: фиксированный шаг 50 000 ₽, покрываем весь диапазон
        step = 50_000
        lo = (min_val // step) * step
        hi = ((max_val // step) + 1) * step + step
        edges = list(range(lo, hi, step))
        if len(edges) < 2:
            edges = [lo, lo + step]

        distribution = []
        for i in range(len(edges) - 1):
            a, b = edges[i], edges[i + 1]
            cnt = sum(1 for s in salaries_sorted if a <= s < b)
            if cnt:
                distribution.append({"from": a, "to": b - 1, "count": cnt})

        return {
            "query": query,
            "count": len(salaries),
            "median": median_val,
            "mean": mean_val,
            "min": min_val,
            "max": max_val,
            "distribution": distribution,
        }


def _parse_salary_value(text: str) -> int | None:
    """Парсит зарплату из строки вида '120 000 ₽', '80–100 тыс. руб.' и т.п."""
    text = text.replace("\xa0", " ").replace(" ", " ")

    # Диапазон — берём среднее
    m = re.search(r"(\d[\d\s]*\d|\d+)\s*[–\-—]\s*(\d[\d\s]*\d|\d+)", text)
    if m:
        lo = int(re.sub(r"\s+", "", m.group(1)))
        hi = int(re.sub(r"\s+", "", m.group(2)))
        val = (lo + hi) // 2
    else:
        # Одиночное число
        m = re.search(r"(\d[\d\s]*\d|\d+)", text)
        if not m:
            return None
        val = int(re.sub(r"\s+", "", m.group(1)))

    # Тысячи: "120 тыс" → 120_000
    if re.search(r"тыс", text, re.IGNORECASE):
        val *= 1000

    # Отсекаем явно невалидные/мусорные значения: ниже 30 000 ₽ обычно
    # стажёрские/неполные ставки, искажающие минимум и медиану.
    if val < 30_000 or val > 10_000_000:
        return None
    return val
