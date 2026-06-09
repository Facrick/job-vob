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
from core.scraper._vacancy import _VacancyMixin

__all__ = ["HHParser", "VacancyInfo", "HumanInteractionEngine"]


class HHParser(_VacancyMixin, _AuthMixin, _NegotiationsMixin, _ApplyMixin):
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
