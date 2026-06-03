"""Клиент официального API hh.ru (https://api.hh.ru) на чистом stdlib.

Преимущества перед парсингом браузером: стабильный JSON, без капчи, без
Playwright. Используется как основной источник; при любой ошибке вызывающий
код (SearchService) откатывается на Playwright-парсер.

Сетевой вызов изолирован в `_get_json`, чтобы маппинг JSON→dict тестировался
офлайн без обращения к сети.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Callable

from core.config import AppConfig
from core.utils import strip_html

# hh.ru требует осмысленный User-Agent, иначе отвечает 403.
_USER_AGENT = "qa-smart-assistant/0.1 (job search helper)"


class HHApiClient:
    BASE = "https://api.hh.ru"

    def __init__(self, config: AppConfig | None = None):
        self.config = config or AppConfig()

    # ── Сеть (единственная точка, мокается в тестах) ───────────────
    def _get_json(self, path: str, params: dict | None = None) -> dict:
        url = f"{self.BASE}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 (доверенный домен)
            return json.loads(resp.read().decode("utf-8"))

    # ── Маппинг JSON → внутренний dict (как у парсера) ─────────────
    @staticmethod
    def _map_salary(salary: dict | None) -> tuple[int | None, int | None]:
        if not salary:
            return None, None
        return salary.get("from"), salary.get("to")

    @staticmethod
    def _map_list_item(item: dict) -> dict:
        s_min, s_max = HHApiClient._map_salary(item.get("salary"))
        employer = (item.get("employer") or {}).get("name") or "Не указана"
        return {
            "id": str(item.get("id")),
            "title": item.get("name", ""),
            "company": employer,
            "salary_min": s_min,
            "salary_max": s_max,
            "description": "",
            "skills": "",
        }

    @staticmethod
    def _map_detail(detail: dict) -> dict:
        description = strip_html(detail.get("description") or "") or "Описание отсутствует."
        skills = ", ".join(
            s.get("name", "") for s in (detail.get("key_skills") or []) if s.get("name")
        ) or "Не указаны"
        return {"description": description, "skills": skills}

    # ── Основной сценарий ──────────────────────────────────────────
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
        if max_vacancies is None:
            max_vacancies = self.config.get("max_vacancies_per_search")

        logging.info(f"🌐 API hh.ru: поиск «{text}»")
        items: list[dict] = []
        for page in range(page_limit):
            params = {
                "text": text, "search_field": "name", "area": area,
                "experience": experience, "period": period,
                "per_page": 20, "page": page,
            }
            if schedule:
                params["schedule"] = schedule
            data = self._get_json("/vacancies", params)
            for it in data.get("items", []):
                items.append(self._map_list_item(it))
                if len(items) >= max_vacancies:
                    break
            if len(items) >= max_vacancies or page + 1 >= data.get("pages", 1):
                break

        total = len(items)
        logging.info(f"🆕 API hh.ru: найдено вакансий: {total}. Загружаю детали...")

        result: list[dict] = []
        for idx, base in enumerate(items, 1):
            label = base["title"][:60]
            logging.info(f"⏳ [API {idx}/{total}] {label}")
            if progress_callback:
                progress_callback(idx, total, label)
            try:
                detail = self._get_json(f"/vacancies/{base['id']}")
                base.update(self._map_detail(detail))
            except Exception as e:
                logging.warning(f"Деталь {base['id']} не загружена: {e}")
            result.append(base)
            if on_vacancy:
                on_vacancy(dict(base))

        logging.info(f"🏁 API hh.ru: готово, вакансий: {len(result)}")
        return result
