"""Оркестратор поиска вакансий через Playwright-парсер hh.ru.

Парсер импортируется лениво (внутри метода), чтобы этот модуль и тесты не
тянули Playwright на этапе импорта.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from core.config import AppConfig


class SearchService:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig()

    def _make_parser(self):
        from core.parser import HHParser  # ленивый импорт: без Playwright на импорте
        return HHParser(self.config)

    async def _search_one(self, *, text: str, **kwargs) -> list[dict]:
        """Выполняет поиск через async Playwright-парсер hh.ru."""
        return await self._make_parser().parse_market_async(text=text, **kwargs)

    async def search(
        self,
        *,
        text: str,
        expand: bool = False,
        period: int = 7,
        area: int = 113,
        experience: str | list[str] = "",
        schedule: str | list[str] = "",
        search_field: str = "name,company_name,description",
        page_limit: int = 1,
        max_vacancies: int | None = None,
        concurrency: int = 3,
        progress_callback: Callable | None = None,
        on_vacancy: Callable | None = None,
        should_cancel: Callable | None = None,
        headless: bool | None = None,
        stats: dict | None = None,
    ) -> list[dict]:
        """Поиск вакансий с опциональным расширением по синонимам (async).

        Если expand=True, запрос дополняется синонимами из core.synonyms.
        Результаты дедуплицируются по vacancy id — одна вакансия не попадёт
        в таблицу дважды даже если найдена по нескольким запросам.
        Детальный разбор карточек идёт параллельно (concurrency вкладок).

        Если передан dict `stats`, он заполняется счётчиками поиска:
          parsed      — всего карточек разобрано парсером;
          duplicates  — отброшено как дубли (по vacancy id);
          filtered    — отсеяно по названию (нерелевантно запросу);
          relevant    — прошло фильтры (передано в on_vacancy).
        """
        from core.synonyms import expand_query, title_matches_query

        queries = expand_query(text) if expand else [text]
        n = len(queries)

        seen_ids: set[str] = set()
        combined: list[dict] = []
        counts = {"parsed": 0, "duplicates": 0, "filtered": 0, "relevant": 0}

        def _relevant(v: dict) -> bool:
            """Отсекает вакансии, где запрос не относится к названию.

            hh.ru ищет по описанию/компании/навыкам, поэтому в выдачу попадают
            нерелевантные вакансии (запрос встретился только в описании).
            Валидируем заголовок против всей группы синонимов исходного запроса.
            """
            title = v.get("title") or v.get("name") or ""
            if title_matches_query(title, text):
                return True
            logging.info(f"⏭️ Пропущено по названию: «{title}»")
            return False

        def _dedup(v: dict) -> None:
            counts["parsed"] += 1
            vid = str(v.get("id") or "")
            if not vid or vid in seen_ids:
                counts["duplicates"] += 1
                return
            seen_ids.add(vid)
            if not _relevant(v):
                counts["filtered"] += 1
                return
            counts["relevant"] += 1
            combined.append(v)
            if on_vacancy:
                on_vacancy(v)

        for qi, q in enumerate(queries, 1):
            if should_cancel and should_cancel():
                break
            if n > 1:
                logging.info(f"🔍 Расширенный поиск {qi}/{n}: «{q}»")

            # Оборачиваем progress_callback, чтобы в статусе отображался текущий запрос
            if progress_callback and n > 1:
                def _pc(idx, total, label="", _q=q, _qi=qi, _n=n):
                    progress_callback(idx, total, f"[{_qi}/{_n} «{_q}»] {label}")
            else:
                _pc = progress_callback

            # _dedup вызывается парсером для каждой вакансии (on_vacancy=_dedup):
            # он дедуплицирует, фильтрует по названию и наполняет combined.
            await self._search_one(
                text=q, period=period, area=area, experience=experience,
                schedule=schedule, search_field=search_field, page_limit=page_limit,
                max_vacancies=max_vacancies, concurrency=concurrency,
                progress_callback=_pc, on_vacancy=_dedup,
                should_cancel=should_cancel, headless=headless,
            )

        if stats is not None:
            stats.update(counts)
        return combined
