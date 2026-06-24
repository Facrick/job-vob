"""core.scraper — Playwright-парсер вакансий hh.ru.

HHParser собирается из миксинов по ответственности:
  _VacancyMixin      — поиск и разбор карточек
  _AuthMixin         — проверка / выполнение авторизации
  _NegotiationsMixin — синхронизация статусов откликов
  _ApplyMixin        — автоотклик с сопроводительным письмом

Используйте:
    from core.scraper import HHParser, VacancyInfo
"""

import random

from core.config import AppConfig
from core.paths import user_path
from core.scraper._apply import _ApplyMixin
from core.scraper._auth import _AuthMixin
from core.scraper._human import HumanInteractionEngine, VacancyInfo
from core.scraper._negotiations import _NegotiationsMixin
from core.scraper._resume_stats import _ResumeStatsMixin
from core.scraper._vacancy import _VacancyMixin
from core.scraper._vacancy_async import _VacancyAsyncMixin

__all__ = ["HHParser", "VacancyInfo", "HumanInteractionEngine"]


class HHParser(
    _VacancyMixin, _VacancyAsyncMixin, _AuthMixin, _NegotiationsMixin,
    _ApplyMixin, _ResumeStatsMixin,
):
    """Парсер вакансий с hh.ru с защитой от блокировки.

    Методы разбиты по файлам-миксинам — см. core/scraper/*.py.
    """

    def __init__(self, config: AppConfig | None = None, proxy_url: str | None = None):
        self.config = config or AppConfig()
        self.human_engine = HumanInteractionEngine(self.config)
        self.proxy = {"server": proxy_url} if proxy_url else None
        self.headless = bool(self.config.get("browser_headless"))
        self.user_data_dir = user_path("data/browser_user_data")

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) "
            "Gecko/20100101 Firefox/125.0",
        ]

    async def _launch_context_async(self, p, headless: bool = True, **kwargs):
        """Async-версия _launch_context для _vacancy_async."""
        from core.scraper._auth import _clear_chromium_locks
        _clear_chromium_locks(str(self.user_data_dir))
        return await p.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=headless,
            user_agent=random.choice(self.user_agents),
            proxy=self.proxy,
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
            **kwargs,
        )

    def _launch_context(self, p, headless: bool = True, **kwargs):
        """Запускает persistent context, предварительно сняв Chromium lock-файлы.

        При переносе профиля между машинами (Windows→Docker/Linux) Chromium
        оставляет SingletonLock с hostname исходной машины — новый процесс
        падает с exitCode=21. Удаляем локи перед каждым запуском.
        """
        from core.scraper._auth import _clear_chromium_locks
        _clear_chromium_locks(str(self.user_data_dir))
        return p.chromium.launch_persistent_context(
            user_data_dir=str(self.user_data_dir),
            headless=headless,
            user_agent=random.choice(self.user_agents),
            proxy=self.proxy,
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
            **kwargs,
        )
