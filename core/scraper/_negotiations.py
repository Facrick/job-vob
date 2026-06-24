"""Синхронизация статусов откликов с hh.ru — миксин для HHParser."""
import logging
import random
import re
from collections.abc import Callable
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from core.scraper._constants import (
    HH_BASE_URL,
    HH_NEGOTIATIONS_URL,
    HH_VACANCY_URL,
    TIMEOUT_NETWORK_IDLE_MS,
    TIMEOUT_PAGE_LOAD_MS,
    TIMEOUT_PAGE_LOAD_SLOW_MS,
    TIMEOUT_SELECTOR_SLOW_MS,
    TIMEOUT_SYNC_PAGE_MS,
)


def _extract_base(url: str) -> str:
    """Возвращает scheme+host из URL, напр. 'https://perm.hh.ru'."""
    try:
        p = urlparse(url)
        return f"{p.scheme}://{p.netloc}"
    except Exception:
        return HH_BASE_URL


class _NegotiationsMixin:
    """Методы проверки статусов откликов по прямым ссылкам на вакансии."""

    # Ключевые слова для определения статуса.
    # Порядок важен: более специфичные — первыми.
    # Одиночные «собеседование» / «интервью» убраны — встречаются в описаниях вакансий.
    _RESP_STATUS_KEYWORDS = [
        # Оффер
        "оффер", "предложение о работе", "job offer",
        # Приглашение — точные фразы статуса
        "приглашение на интервью", "вас пригласили", "приглашён", "приглашен на",
        "телефонное интервью",
        # Отказ
        "отказ", "отклонен", "не подош",
        # Отклик / просмотр — статусные формулировки
        "ваш отклик", "вы уже откликнулись", "отклик рассматривается",
        "отклик просмотрен", "отклик отправлен", "просмотрен работодателем",
        "отклик на рассмотрении",
    ]

    # Разделители начала описания вакансии — всё ДО них считается «шапкой» (apply-зоной)
    _DESC_MARKERS = [
        "обязанности", "требования", "условия работы", "о компании",
        "что мы предлагаем", "чем предстоит заниматься",
    ]

    # Адрес страницы «Отклики» (список переговоров соискателя).
    _NEGOTIATIONS_URL = HH_NEGOTIATIONS_URL
    _NEG_MAX_PAGES = 20  # предохранитель от бесконечной пагинации

    # Маппинг статуса из КАРТОЧКИ страницы «Отклики» → канонический текст для
    # map_hh_status. На списке статусы — чистые («Приглашение», «Отказ»,
    # «Отклик доставлен»…), поэтому матчим шире, чем на странице вакансии.
    # Порядок важен: более «сильные»/специфичные — первыми.
    _NEG_LIST_KEYWORDS: list[tuple[str, str]] = [
        ("вам отказали",          "отказ"),
        ("отказ",                 "отказ"),
        ("отклонен",              "отказ"),
        ("вам предложили работу", "предложение о работе"),
        ("предложение о работе",  "предложение о работе"),
        ("приглашение",           "приглашение на интервью"),
        ("пригласил",             "вас пригласили"),
        ("отклик доставлен",      "отклик отправлен"),
        ("резюме доставлено",     "отклик отправлен"),
        ("доставлен",             "отклик отправлен"),
        ("просмотрен",            "отклик просмотрен"),
        ("рассматривается",       "отклик рассматривается"),
        ("не просмотрен",         "отклик отправлен"),
        ("отклик",                "ваш отклик"),
    ]

    def fetch_negotiations(
        self,
        vacancy_ids: list[str],
        progress_callback: Callable[[int, int, str], None] | None = None,
    ) -> list[dict]:
        """Читает статусы откликов со страницы «Отклики» hh.ru.

        Основной путь — список /applicant/negotiations (быстро, достоверно).
        Если список не дал результатов (изменилась вёрстка) — фолбэк на
        поштучный обход страниц вакансий из CRM.

        Возвращает список {vacancy_id, hh_status, title, company}.
        Поднимает RuntimeError если не авторизован.
        """
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            # Открываем ОДИН persistent context сразу — не вызываем _check_logged_in
            # отдельно, так как он открывает свой context на тот же user_data_dir
            # и закрывает его, из-за чего следующий context стартует без сессии.
            ctx = self._launch_context(
                p, headless=False,
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            try:
                ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    "window.chrome={runtime:{}};"
                    "Object.defineProperty(navigator,'languages',{get:()=>['ru-RU','ru']});"
                    "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
                )
            except Exception:
                pass

            try:
                page = ctx.new_page()

                # Открываем страницу откликов — браузер уже с сессией из user_data_dir.
                # Если не авторизован — hh.ru редиректит на /account/login.
                page.goto(
                    self._NEGOTIATIONS_URL,
                    wait_until="domcontentloaded",
                    timeout=TIMEOUT_PAGE_LOAD_MS,
                )

                # Проверяем авторизацию по URL после редиректа
                if "/account/login" in page.url:
                    raise RuntimeError(
                        "Не авторизован на hh.ru. "
                        "Войдите через кнопку «Войти» и повторите синхронизацию."
                    )

                real_base = _extract_base(page.url)
                logging.info(f"[Sync] реальный домен hh.ru: {real_base}")

                # Если словили vpncheck — ждём ручного прохождения.
                if self._is_blocked_page(page):
                    self._wait_for_unblock(page, self._NEGOTIATIONS_URL)
                    real_base = _extract_base(page.url)

                results = self._fetch_from_negotiations_list(page, progress_callback, real_base)
                if results:
                    return results
                logging.warning(
                    "[Sync] Список «Отклики» пуст/не распознан — фолбэк на обход вакансий."
                )
                return self._fetch_via_vacancy_pages(page, vacancy_ids, progress_callback)
            finally:
                ctx.close()

    def _wait_through_vpncheck(self, page, target_url: str) -> None:
        """Пережидает анти-бот-страницу hh.ru `/vpncheeck`.

        Сначала ждёт авто-прохождения JS-проверки (~5 с). Если hh.ru не вернул
        сам — открывает окно для ручного прохождения через _wait_for_unblock.
        """
        try:
            cur = page.url
        except Exception:
            cur = ""
        if "vpncheeck" not in cur and "vpncheck" not in cur:
            return

        logging.info("[NegList] vpncheeck hh.ru — жду авто-прохождения JS-проверки…")
        # Даём hh.ru ~5 сек на автоматическое прохождение JS-редиректа
        for _ in range(5):
            page.wait_for_timeout(1000)
            try:
                cur = page.url
            except Exception:
                cur = ""
            if "vpncheeck" not in cur and "vpncheck" not in cur:
                logging.info("[NegList] vpncheeck пройден автоматически")
                return

        # JS-редирект не сработал — нужно ручное прохождение
        self._wait_for_unblock(page, target_url)

        """Парсит HTML страницы /applicant/negotiations после рендера React.

        Структура карточки:
          data-qa="negotiations-item"
            <a href="/vacancy/ID?...">  ← первая ссылка = вакансия
            data-qa="negotiations-item-vacancy"  ← название
            data-qa="negotiations-item-company"  ← компания
            data-qa="negotiations-tag negotiations-item-{status}"  ← статус
        """
        soup = BeautifulSoup(html, "html.parser")
        results: list[dict] = []
        seen: set[str] = set()

        for card in soup.find_all(attrs={"data-qa": "negotiations-item"}):
            # vacancy_id из первой ссылки /vacancy/ID
            vid = ""
            for a in card.find_all("a", href=True):
                m = re.search(r"/vacancy/(\d+)", a["href"])
                if m:
                    vid = m.group(1)
                    break
            if not vid or vid in seen:
                continue
            seen.add(vid)

            title_el = card.find(attrs={"data-qa": "negotiations-item-vacancy"})
            title = title_el.get_text(strip=True) if title_el else ""

            company_el = card.find(attrs={"data-qa": "negotiations-item-company"})
            company = company_el.get_text(strip=True) if company_el else ""

            # Статус: ищем тег с data-qa содержащим "negotiations-tag"
            hh_status = ""
            for tag_el in card.find_all(attrs={"data-qa": re.compile(r"negotiations-tag")}):
                dqa = tag_el.get("data-qa", "")
                for suffix, mapped in self._NEG_TAG_STATUS:
                    if suffix in dqa:
                        hh_status = mapped
                        break
                if hh_status:
                    break

            logging.info(
                f"[NegPage:{vid}] «{title[:40]}» / {company} → «{hh_status or '?'}»"
            )
            results.append({
                "vacancy_id": vid,
                "hh_status":  hh_status,
                "title":      title[:80],
                "company":    company,
            })

        return results

    def _fetch_from_negotiations_list(
        self, page, progress_callback: Callable | None = None,
        real_base: str = HH_BASE_URL,
    ) -> list[dict]:
        """Открывает страницу /applicant/negotiations и парсит список откликов.

        Ждёт рендера React (data-qa=negotiations-item), затем читает HTML.
        Пагинирует через кнопку «Ещё».
        """
        neg_url = f"{real_base}/applicant/negotiations"
        try:
            # Переходим на страницу откликов через goto — это надёжнее чем
            # надеяться что мы уже там после редиректа.
            page.goto(neg_url, wait_until="networkidle", timeout=TIMEOUT_PAGE_LOAD_SLOW_MS)
            self._wait_through_vpncheck(page, neg_url)

            # Ждём пока React отрисует карточки откликов.
            # Пробуем несколько возможных селекторов — hh.ru мог изменить data-qa.
            selectors = [
                '[data-qa="negotiations-item"]',
                '[data-qa^="negotiations-"]',
                'a[href*="/vacancy/"]',
            ]
            loaded = False
            for sel in selectors:
                try:
                    page.wait_for_selector(sel, timeout=TIMEOUT_SELECTOR_SLOW_MS)
                    loaded = True
                    logging.info(f"[NegPage] страница загружена, найден: {sel}")
                    break
                except Exception:
                    continue

            if not loaded:
                # Последняя попытка: просто подождём загрузки сети и проверим HTML
                page.wait_for_timeout(5000)
                html_check = page.content()
                if "/vacancy/" not in html_check:
                    logging.warning(
                        f"[NegPage] страница откликов не загрузилась. "
                        f"URL: {page.url}, HTML длина: {len(html_check)}"
                    )
                    self._diag_negotiations_html(page, html_check, 0)
                    return []
                logging.info("[NegPage] загрузка по fallback (ссылки на вакансии есть)")

        except Exception as e:
            logging.warning(f"[NegPage] ошибка при загрузке страницы откликов: {e}")
            return []

        results: list[dict] = []
        seen_ids: set[str] = set()
        _MAX_LOAD_MORE = 9  # первая загрузка + 9 кликов «Ещё» = 10 «страниц»

        # Читаем первую порцию карточек
        html = page.content()
        batch = self._parse_negotiations_page_html(html)
        for item in batch:
            if item["vacancy_id"] not in seen_ids:
                seen_ids.add(item["vacancy_id"])
                results.append(item)
        logging.info(f"[NegPage] загрузка 1: карточек={len(results)}")

        # Кликаем кнопку «Ещё» до _MAX_LOAD_MORE раз — hh.ru дозагружает карточки
        # в тот же список (infinite scroll), а не переходит на новую страницу.
        for click_num in range(1, _MAX_LOAD_MORE + 1):
            more_btn = page.locator('[data-qa="moreItems-button"]')
            if more_btn.count() == 0:
                logging.info(f"[NegPage] кнопка «Ещё» не найдена — все отклики загружены")
                break

            try:
                more_btn.first.scroll_into_view_if_needed()
                more_btn.first.click()
                # Ждём появления новых карточек — счётчик должен вырасти
                for _ in range(20):  # до 10 секунд
                    page.wait_for_timeout(500)
                    html = page.content()
                    batch = self._parse_negotiations_page_html(html)
                    new_ids = [i for i in batch if i["vacancy_id"] not in seen_ids]
                    if new_ids:
                        break

                new = 0
                for item in batch:
                    if item["vacancy_id"] not in seen_ids:
                        seen_ids.add(item["vacancy_id"])
                        results.append(item)
                        new += 1

                logging.info(f"[NegPage] загрузка {click_num + 1}: всего карточек={len(batch)}, новых={new}")

                if progress_callback and results:
                    progress_callback(len(results), len(results),
                                      results[-1].get("title") or "")

                if new == 0:
                    logging.info("[NegPage] новых карточек нет — все отклики загружены")
                    break

            except Exception as e:
                logging.warning(f"[NegPage] ошибка при загрузке «Ещё» ({click_num}): {e}")
                break

        logging.info(f"[NegPage] итого откликов: {len(results)}")
        return results

    def _diag_negotiations_html(self, page, html: str, page_num: int) -> None:
        """Лог реальной структуры страницы «Отклики», когда карточки не нашлись."""
        try:
            soup = BeautifulSoup(html, "html.parser")
            all_a = soup.find_all("a")
            vac_hrefs = [a.get("href") for a in all_a
                         if a.get("href") and "/vacancy/" in a["href"]]
            # Все vacancy-id, встречающиеся в HTML (вкл. встроенный JSON).
            ids_in_html = sorted(set(re.findall(r"/vacancy/(\d+)", html)))[:10]
            json_ids = sorted(set(re.findall(r'"vacancyId"\s*:\s*"?(\d+)', html)))[:10]
            # Топ data-qa, относящихся к откликам/карточкам.
            dqa = {}
            for el in soup.find_all(attrs={"data-qa": True}):
                key = el["data-qa"].split()[0] if el["data-qa"] else ""
                if any(w in key.lower() for w in
                       ("negotiat", "response", "resume", "vacancy", "serp", "item", "topic")):
                    dqa[key] = dqa.get(key, 0) + 1
            top_dqa = sorted(dqa.items(), key=lambda kv: -kv[1])[:12]

            try:
                cur_url = page.url
            except Exception:
                cur_url = "?"

            logging.info(f"[NegList:diag] url={cur_url} html_len={len(html)}")
            logging.info(
                f"[NegList:diag] a_total={len(all_a)} vac_anchors={len(vac_hrefs)} "
                f"sample_href={vac_hrefs[:3]}"
            )
            logging.info(
                f"[NegList:diag] vacancy_ids_in_html={ids_in_html} "
                f'"vacancyId"_json={json_ids}'
            )
            logging.info(
                f"[NegList:diag] initial_state={'HH-Lux-InitialState' in html} "
                f"negotiations_kw={'negotiation' in html.lower()} "
                f"empty_kw={'нет откликов' in html.lower() or 'пока нет' in html.lower()}"
            )
            logging.info(f"[NegList:diag] data-qa(top)={top_dqa}")
        except Exception as exc:
            logging.warning(f"[NegList:diag] не удалось собрать диагностику: {exc}")

    def _fetch_via_vacancy_pages(
        self, page, vacancy_ids: list[str],
        progress_callback: Callable | None = None,
    ) -> list[dict]:
        """Поштучный обход страниц вакансий через Playwright.

        Проверяем только вакансии со статусом applied/interview — те на которые
        откликнулись и у которых статус ещё может измениться.
        discovered/processed — не откликались, offer/rejected — финальные статусы.
        """
        # Пропускаем только финальные статусы — там уже нечего обновлять
        _SKIP_STATUSES = {"offer", "rejected"}
        try:
            from core.database import VacancyRepository
            repo = VacancyRepository()
            active_ids = [
                v["id"] for v in repo.get_vacancies_filtered("all")
                if v.get("status") not in _SKIP_STATUSES
                and v.get("id") in set(vacancy_ids)
            ]
        except Exception:
            active_ids = vacancy_ids  # если БД недоступна — обходим всё

        if not active_ids:
            logging.info("[Sync] все вакансии в финальных статусах — обход не нужен.")
            return []

        logging.info(
            f"[Sync] поштучный обход {len(active_ids)} вакансий "
            f"(пропущено {len(vacancy_ids) - len(active_ids)} финальных)"
        )
        results: list[dict] = []
        total = len(active_ids)
        vacancy_ids = active_ids
        for idx, vid in enumerate(vacancy_ids, 1):
            url = HH_VACANCY_URL.format(vacancy_id=vid)
            logging.info(f"[Sync] {idx}/{total} → {url}")
            if progress_callback:
                progress_callback(idx, total, f"загружаю {vid}…")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_SYNC_PAGE_MS)
                try:
                    page.wait_for_selector(
                        "[data-qa*='response'],[data-qa*='status'],[data-qa*='vacancy-title']",
                        timeout=TIMEOUT_NETWORK_IDLE_MS,
                    )
                except Exception:
                    pass
                page.wait_for_timeout(1000)
                item = self._check_vacancy_response_html(page.content(), vid)
                results.append(item)
                logging.info(
                    f"[Sync] {vid}: статус = «{item['hh_status'] or 'не определён'}»"
                )
                if progress_callback:
                    company = item.get("company", "")
                    title = item.get("title", "")
                    label = f"{company} — {title}" if company and title else title or vid
                    progress_callback(idx, total, label)
            except Exception as exc:
                logging.warning(f"[Sync] Ошибка при проверке {vid}: {exc}")
                results.append({"vacancy_id": vid, "hh_status": "",
                                "title": "", "company": ""})
        return results

    # Прямой маппинг текста кнопки/статуса hh.ru на наш внутренний статус.
    # Ключ — подстрока текста (lower), значение — строка для map_hh_status.
    # Порядок важен: более специфичные — первыми.
    _BUTTON_STATUS_MAP: list[tuple[str, str]] = [
        # ── Отказ ──────────────────────────────────────────────────────────────
        ("вам отказали",            "отказ"),
        ("отказ",                   "отказ"),
        ("отклонен",                "отказ"),
        ("не подош",                "отказ"),
        # ── Оффер ──────────────────────────────────────────────────────────────
        ("вам предложили работу",   "предложение о работе"),
        ("предложение о работе",    "предложение о работе"),
        ("job offer",               "предложение о работе"),
        ("оффер принят",            "предложение о работе"),
        # ── Собеседование ──────────────────────────────────────────────────────
        ("вас пригласили",          "вас пригласили"),
        ("приглашение на интервью", "приглашение на интервью"),
        ("приглашён",               "приглашён"),
        ("телефонное интервью",     "телефонное интервью"),
        # ── Отклик отправлен / на рассмотрении ────────────────────────────────
        ("вы откликнулись",         "вы уже откликнулись"),
        ("отклик другим резюме",    "вы уже откликнулись"),  # кнопка после отклика
        ("отклик отправлен",        "отклик отправлен"),
        ("отклик рассматривается",  "отклик рассматривается"),
        ("отклик просмотрен",       "отклик просмотрен"),
        ("ваш отклик",              "ваш отклик"),
        ("просмотрен работодателем","просмотрен работодателем"),
        # ── Можно откликнуться (кнопка активна) ────────────────────────────────
        ("откликнуться",            "можно откликнуться"),
    ]

    # Баннер-статус hh.ru («Вы откликнулись», «Вам отказали» и т.п.) — однозначный
    # сигнал, появляется ТОЛЬКО для твоего отклика на этой вакансии (в описаниях и
    # блоках рекомендаций его нет). Порядок: терминальные/важные — первыми.
    _STATUS_BANNER: list[tuple[str, str]] = [
        ("вам отказали",          "отказ"),
        ("вам предложили работу", "предложение о работе"),
        ("вас пригласили",        "вас пригласили"),
        ("вы откликнулись",       "вы уже откликнулись"),
    ]

    def _check_vacancy_response_html(self, html: str, vacancy_id: str) -> dict:
        """Извлекает статус отклика из HTML страницы вакансии.

        Главный источник истины — текст кнопки/статуса у блока отклика.
        hh.ru меняет текст кнопки в зависимости от состояния отклика:
          «Откликнуться» → нет отклика
          «Вы откликнулись» → отклик отправлен
          «Вас пригласили» → собеседование
          «Вам отказали» → отказ
          «Вам предложили работу» → оффер
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

        # Проверяем не закрыта ли вакансия — ТОЛЬКО по специфичному маркеру hh.ru,
        # а не по тексту всей страницы. Раньше фразы «в архиве» / «вакансия закрыта»
        # ловились из блоков «Похожие вакансии», футера и т.п. → ложное «закрыта».
        archived = soup.find(attrs={"data-qa": re.compile(
            r"vacancy-archive|vacancy-deleted|vacancy-not-found", re.I)})
        if archived is None:
            # Запасной маркер: явный заголовок-уведомление в шапке страницы.
            head_text = " ".join(
                t.get_text(" ", strip=True).lower()
                for t in soup.find_all(["h1", "h2"], limit=4)
            )
            if any(m in head_text for m in (
                "вакансия не найдена", "вакансия удалена", "вакансия в архиве",
                "vacancy not found",
            )):
                archived = True
        if archived:
            return {"vacancy_id": vacancy_id, "hh_status": "закрыта",
                    "title": title, "company": company}

        status_text = ""

        # ── Диагностика: собираем ВСЕ элементы, связанные с откликом, и их текст.
        # Видно во вкладке «Логи» — чтобы точно понять, что hh.ru реально отдаёт.
        _diag = []
        for elem in soup.find_all(
            attrs={"data-qa": re.compile(r"response|negotiat|applicant", re.I)}
        ):
            dq = elem.get("data-qa", "")
            txt = elem.get_text(" ", strip=True)[:60]
            if dq:
                _diag.append(f"{dq}=«{txt}»")

        # ── ШАГ 0: баннер-статус по тексту страницы (самый надёжный сигнал) ──
        # hh.ru показывает «Вы откликнулись» / «Вам отказали» / «Вам предложили
        # работу» / «Вас пригласили» в баннере с ⓘ над кнопками. Эти фразы
        # уникальны для твоего отклика, поэтому скан текста безопасен.
        full_text = soup.get_text(" ", strip=True).lower()
        for phrase, mapped in self._STATUS_BANNER:
            if phrase in full_text:
                status_text = mapped
                logging.debug(f"[Sync:{vacancy_id}] баннер: «{phrase}» → {mapped}")
                break

        # ── ШАГ 1: читаем текст кнопки / статусного элемента у блока отклика ──
        # Это самый надёжный способ: hh.ru сам пишет «Вы откликнулись» / «Откликнуться».
        btn_dqa_patterns = [
            r"vacancy-response-link-top",
            r"vacancy-response-link-bottom",
            r"vacancy-response-link",
            r"vacancy-response$",
        ]
        if not status_text:
            for pat in btn_dqa_patterns:
                btn = soup.find(attrs={"data-qa": re.compile(pat, re.I)})
                if btn:
                    btn_text = btn.get_text(strip=True).lower()
                    logging.debug(f"[Sync:{vacancy_id}] кнопка ({pat}): «{btn_text}»")
                    for keyword, mapped in self._BUTTON_STATUS_MAP:
                        if keyword in btn_text:
                            status_text = mapped
                            break
                    if status_text:
                        break

        # ── ШАГ 2: отдельный элемент статуса отклика (data-qa) ────────────────
        if not status_text:
            for dqa in [
                "vacancy-response-status", "response-status",
                "negotiations-status", "negotiation-status",
                "applicant-status", "vacancy-applicant-status",
            ]:
                tag = soup.find(attrs={"data-qa": re.compile(dqa, re.I)})
                if tag:
                    tag_text = tag.get_text(strip=True).lower()
                    for keyword, mapped in self._BUTTON_STATUS_MAP:
                        if keyword in tag_text:
                            status_text = mapped
                            break
                    if status_text:
                        break

        # ── ШАГ 3: текст ближайших родительских элементов кнопки ──────────────
        # Только если предыдущие шаги ничего не дали.
        # Ограничиваем поиск 2 уровнями вверх — не трогаем описание вакансии.
        if not status_text:
            btn = soup.find(attrs={"data-qa": re.compile(r"vacancy-response-link", re.I)})
            if btn:
                node = btn
                for _ in range(2):
                    node = node.parent
                    if node is None:
                        break
                    zone_text = node.get_text(" ", strip=True).lower()
                    for keyword, mapped in self._BUTTON_STATUS_MAP:
                        # Пропускаем «откликнуться» на этом шаге — слишком широко
                        if keyword == "откликнуться":
                            continue
                        if keyword in zone_text:
                            status_text = mapped
                            break
                    if status_text:
                        break

        # ── ШАГ 4: статус не распознан → оставляем ПУСТЫМ ─────────────────────
        # РАНЬШЕ здесь при наличии кнопки отклика молча выставлялось
        # «можно откликнуться» (→ DISCOVERED). Но наличие элемента
        # vacancy-response-link НЕ означает отсутствие отклика: после отклика
        # hh.ru часто оставляет тот же data-qa, лишь меняя текст на
        # «Вы откликнулись». Если текст не успел прогрузиться, мы НЕ знаем
        # статус — и раньше ошибочно откатывали applied/interview/offer назад
        # в «Новая». При политике «hh.ru — источник истины» это давало ложные
        # сбросы. Теперь в неоднозначном случае возвращаем пустой статус →
        # sync пропустит вакансию и не тронет её текущий этап.
        # Реальную активную кнопку «Откликнуться» уже распознаёт ШАГ 1 по тексту.

        # ── Отладка ────────────────────────────────────────────────────────────
        if not status_text:
            all_dqa = [t.get("data-qa", "") for t in soup.find_all(attrs={"data-qa": True})]
            relevant = [d for d in all_dqa if any(
                w in d.lower() for w in ("status", "response", "negotiat", "applicant", "apply")
            )]
            logging.debug(f"[Sync:{vacancy_id}] статус не определён. data-qa: {relevant or '—'}")

        # Ключевая диагностическая строка — попадает во вкладку «Логи» (INFO).
        logging.info(
            f"[Sync:{vacancy_id}] «{title[:40]}» сигналы={_diag or '—'} "
            f"→ статус=«{status_text or 'не определён'}»"
        )
        return {
            "vacancy_id": vacancy_id,
            "hh_status": status_text,
            "title": title,
            "company": company,
        }
