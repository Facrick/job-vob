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

    def search(
        self,
        *,
        text: str,
        period: int = 7,
        area: int = 113,
        experience: str = "between1And3",
        schedule: str = "remote",
        page_limit: int = 1,
        max_vacancies: int | None = None,
        progress_callback: Callable | None = None,
        on_vacancy: Callable | None = None,
    ) -> list[dict]:
        kwargs = dict(
            text=text, period=period, area=area, experience=experience,
            schedule=schedule, page_limit=page_limit,
            max_vacancies=max_vacancies, progress_callback=progress_callback,
            on_vacancy=on_vacancy,
        )

        if self.config.get("use_official_api"):
            try:
                vacancies = self._make_api().search(**kwargs)
                if vacancies:
                    return vacancies
                logging.warning("API hh.ru вернул 0 вакансий — переключаюсь на парсер (фолбэк).")
            except Exception as e:
                logging.warning(f"API hh.ru недоступен ({e}) — переключаюсь на парсер (фолбэк).")

        # Фолбэк (или API отключён в настройках)
        return self._make_parser().parse_market(**kwargs)
