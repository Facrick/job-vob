"""Синхронизация статусов откликов с hh.ru — миксин для HHParser."""
import logging
import random
import re
from collections.abc import Callable

from bs4 import BeautifulSoup


class _NegotiationsMixin:
    """Методы проверки статусов откликов по прямым ссылкам на вакансии."""

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
        from playwright.sync_api import sync_playwright
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
                    # Показываем «идёт загрузка» пока страница не открылась
                    if progress_callback:
                        progress_callback(idx, total, f"загружаю {vid}…")

                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=25000)
                        page.wait_for_timeout(1200)
                        html = page.content()
                        item = self._check_vacancy_response_html(html, vid)
                        results.append(item)
                        logging.info(
                            f"[Sync] {vid}: статус = «{item['hh_status'] or 'не определён'}»"
                        )
                        # Обновляем прогресс с реальным названием вакансии
                        if progress_callback:
                            company = item.get("company", "")
                            title   = item.get("title", "")
                            label = f"{company} — {title}" if company and title else title or vid
                            progress_callback(idx, total, label)
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
