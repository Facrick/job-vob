"""Оркестратор источников вакансий: официальный API hh.ru → Playwright-парсер.

Стратегия (выбрана пользователем): API — основной источник; при ошибке или
пустом ответе ПРОЗРАЧНО используется проверенный парсер. Поиск не ломается,
даже если API недоступен или изменился.

Парсер импортируется лениво (внутри метода), чтобы этот модуль и тесты не
тянули Playwright на этапе импорта.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

from core.api_client import HHApiClient
from core.config import AppConfig


class SearchService:
    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig()

    # Фабрики вынесены отдельно — удобно подменять в тестах.
    def _make_api(self) -> HHApiClient:
        return HHApiClient(self.config)

    def _make_parser(self):
        from core.parser import HHParser  # ленивый импорт: без Playwright на импорте
        return HHParser(self.config)

    def _search_one(self, *, text: str, **kwargs) -> list[dict]:
        """Выполняет поиск по одному запросу через API → парсер (фолбэк)."""
        kw = dict(text=text, **kwargs)
        if self.config.get("use_official_api"):
            try:
                vacancies = self._make_api().search(**kw)
                if vacancies:
                    return vacancies
                logging.warning(
                    f"API hh.ru вернул 0 вакансий для «{text}» — переключаюсь на парсер."
                )
            except Exception as e:
                logging.warning(
                    f"API hh.ru недоступен ({e}) — переключаюсь на парсер (фолбэк)."
                )
        return self._make_parser().parse_market(**kw)

    def search(
        self,
        *,
        text: str,
        expand: bool = False,
        period: int = 7,
        area: int = 113,
        experience: str = "between1And3",
        schedule: str = "remote",
        page_limit: int = 1,
        max_vacancies: int | None = None,
        progress_callback: Callable | None = None,
        on_vacancy: Callable | None = None,
    ) -> list[dict]:
        """Поиск вакансий с опциональным расширением по синонимам.

        Если expand=True, запрос дополняется синонимами из core.synonyms.
        Результаты дедуплицируются по vacancy id — одна вакансия не попадёт
        в таблицу дважды даже если найдена по нескольким запросам.
        """
        from core.synonyms import expand_query

        queries = expand_query(text) if expand else [text]
        n = len(queries)

        seen_ids: set[str] = set()
        combined: list[dict] = []

        def _dedup(v: dict) -> None:
            vid = str(v.get("id") or "")
            if vid and vid not in seen_ids:
                seen_ids.add(vid)
                combined.append(v)
                if on_vacancy:
                    on_vacancy(v)

        for qi, q in enumerate(queries, 1):
            if n > 1:
                logging.info(f"🔍 Расширенный поиск {qi}/{n}: «{q}»")

            # Оборачиваем progress_callback, чтобы в статусе отображался текущий запрос
            if progress_callback and n > 1:
                def _pc(idx, total, label="", _q=q, _qi=qi, _n=n):
                    progress_callback(idx, total, f"[{_qi}/{_n} «{_q}»] {label}")
            else:
                _pc = progress_callback

            for v in self._search_one(
                text=q, period=period, area=area, experience=experience,
                schedule=schedule, page_limit=page_limit,
                max_vacancies=max_vacancies, progress_callback=_pc,
                on_vacancy=_dedup,
            ):
                vid = str(v.get("id") or "")
                if vid and vid not in seen_ids:
                    seen_ids.add(vid)
                    combined.append(v)

        return combined
