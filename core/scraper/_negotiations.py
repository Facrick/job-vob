"""Синхронизация статусов откликов с hh.ru — миксин для HHParser."""
import logging
import random
import re
from collections.abc import Callable

from bs4 import BeautifulSoup


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
    _NEGOTIATIONS_URL = "https://hh.ru/applicant/negotiations"
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
                locale="ru-RU",
                timezone_id="Europe/Moscow",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            # Стелс: маскируем признаки headless/automation, на которые смотрит
            # анти-бот hh.ru (/vpncheeck). Снижает вероятность редиректа на проверку.
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
                results = self._fetch_from_negotiations_list(page, progress_callback)
                if results:
                    return results
                logging.warning(
                    "[Sync] Список «Отклики» пуст/не распознан — фолбэк на обход вакансий."
                )
                return self._fetch_via_vacancy_pages(page, vacancy_ids, progress_callback)
            finally:
                ctx.close()

    _NEG_LOAD_ATTEMPTS = 3  # ретраи загрузки одной страницы списка

    def _wait_through_vpncheck(self, page, target_url: str) -> None:
        """Пережидает анти-бот-страницу hh.ru `/vpncheeck`.

        hh.ru при заходе на «чувствительные» страницы (отклики) может перебросить
        на /vpncheeck с JS-проверкой и авто-возвратом по backUrl. Ждём возврата;
        если застряли — повторно переходим на целевой URL.
        """
        for _ in range(8):  # ~до 24с суммарно
            try:
                cur = page.url
            except Exception:
                cur = ""
            if "vpncheeck" not in cur and "vpncheck" not in cur:
                return
            logging.info("[NegList] анти-бот hh.ru (/vpncheeck) — жду прохождения проверки…")
            page.wait_for_timeout(2500)
            cur = page.url
            if "vpncheeck" in cur or "vpncheck" in cur:
                # Не вернулись сами — пробуем перейти на отклики ещё раз.
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass

    def _load_negotiations_page(self, page, page_num: int) -> str:
        """Грузит страницу списка с ретраями: ждём появления ссылок на вакансии.

        Список рендерится JS — без ожидания мы читаем пустой DOM. Делаем до
        _NEG_LOAD_ATTEMPTS попыток (перезагрузка + ожидание), возвращаем HTML
        как только в нём появились ссылки `/vacancy/...`, иначе — последний HTML.
        """
        url = f"{self._NEGOTIATIONS_URL}?page={page_num}"
        last_html = ""
        for attempt in range(1, self._NEG_LOAD_ATTEMPTS + 1):
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Анти-бот hh.ru: может перебросить на /vpncheeck с авто-возвратом
                # на negotiations после JS-проверки. Ждём, пока вернёмся обратно.
                self._wait_through_vpncheck(page, url)
                # Ждём карточки откликов или ссылку на вакансию.
                try:
                    page.wait_for_selector("a[href*='/vacancy/']", timeout=8000)
                except Exception:
                    pass
                # Догружаем ленивый список прокруткой.
                for _ in range(5):
                    page.mouse.wheel(0, 5000)
                    page.wait_for_timeout(400)
                try:
                    page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass
                page.wait_for_timeout(600)
                last_html = page.content()
                if "/vacancy/" in last_html:
                    if attempt > 1:
                        logging.info(f"[NegList] страница {page_num + 1}: успех с попытки {attempt}")
                    return last_html
                logging.warning(
                    f"[NegList] страница {page_num + 1}: ссылок не найдено "
                    f"(попытка {attempt}/{self._NEG_LOAD_ATTEMPTS}), повтор…"
                )
                page.wait_for_timeout(1500 * attempt)
            except Exception as exc:
                logging.warning(
                    f"[NegList] страница {page_num + 1}: ошибка загрузки "
                    f"(попытка {attempt}/{self._NEG_LOAD_ATTEMPTS}): {exc}"
                )
                page.wait_for_timeout(1500 * attempt)
        return last_html

    def _fetch_from_negotiations_list(
        self, page, progress_callback: Callable | None = None
    ) -> list[dict]:
        """Собирает отклики со страницы «Отклики».

        Список грузится отдельным JSON-запросом (React-SPA), поэтому ловим
        сетевые ответы и парсим JSON. HTML-разбор оставлен как запасной.
        """
        captured: list[tuple[str, object]] = []

        def _on_response(resp):
            try:
                url = resp.url.lower()
                ct = (resp.headers or {}).get("content-type", "")
                if "json" in ct and ("negotiat" in url or "/shards/" in url
                                      or "applicant" in url):
                    captured.append((resp.url, resp.json()))
            except Exception:
                pass

        page.on("response", _on_response)
        try:
            # Один заход на список — он сам подтянет JSON всех откликов.
            html = self._load_negotiations_page(page, 0)
            page.wait_for_timeout(2000)  # даём JSON-запросам долететь
        finally:
            try:
                page.remove_listener("response", _on_response)
            except Exception:
                pass

        # Диагностика пойманных JSON — чтобы увидеть реальный эндпоинт/структуру.
        for url, data in captured[:8]:
            top = list(data.keys())[:12] if isinstance(data, dict) else type(data).__name__
            logging.info(f"[NegList:json] {url[:90]} keys={top}")

        results = self._extract_from_neg_json(captured, progress_callback)
        if results:
            logging.info(f"[NegList] из JSON получено откликов: {len(results)}")
            return results

        # Фолбэк: вдруг что-то всё же отрендерилось в HTML.
        logging.warning("[NegList] JSON откликов не распознан — пробую HTML-разбор.")
        results = []
        seen: set[str] = set()
        for page_num in range(self._NEG_MAX_PAGES):
            html = self._load_negotiations_page(page, page_num)
            if not html or "/vacancy/" not in html:
                logging.warning(
                    f"[NegList] страница {page_num + 1}: ссылок на вакансии нет — стоп."
                )
                break

            items = self._parse_negotiations_list(html)

            # Диагностика, если карточек не нашли — чтобы понять реальную верстку.
            if not items:
                self._diag_negotiations_html(page, html, page_num)

            new_on_page = 0
            for it in items:
                vid = it["vacancy_id"]
                if vid in seen:
                    continue
                seen.add(vid)
                results.append(it)
                new_on_page += 1
                if progress_callback:
                    progress_callback(len(results), len(results),
                                      it.get("title") or vid)

            logging.info(
                f"[NegList] страница {page_num + 1}: карточек={len(items)}, "
                f"новых={new_on_page}, всего={len(results)}"
            )
            # Нет новых откликов на странице → пагинация закончилась.
            if new_on_page == 0:
                break

        return results

    # state.id из данных hh.ru → канонический текст для map_hh_status.
    _NEG_STATE_ID_TO_TEXT: dict[str, str] = {
        "response":   "вы уже откликнулись",
        "invitation": "приглашение на интервью",
        "interview":  "приглашение на интервью",
        "discard":    "вам отказали",
        "discard_by_employer": "вам отказали",
        "offer":      "вам предложили работу",
    }

    def _extract_from_neg_json(
        self, captured: list[tuple[str, object]],
        progress_callback: Callable | None = None,
    ) -> list[dict]:
        """Достаёт отклики из пойманных JSON-ответов hh.ru.

        Ищет объекты с ссылкой на вакансию (vacancy.id / vacancyId) и статусом
        (state.id / state.name / status). Схему точно не знаем — берём широко и
        логируем образец первого найденного объекта для доточки.
        """
        found: dict[str, dict] = {}
        sample_logged = [False]

        def _status_text(node: dict) -> tuple[str, str]:
            """→ (canonical_text_for_map, raw_for_log)."""
            state = node.get("state") or node.get("status") or node.get("topicState")
            sid, sname = "", ""
            if isinstance(state, dict):
                sid = str(state.get("id") or state.get("state") or "").lower()
                sname = str(state.get("name") or state.get("title") or "")
            elif isinstance(state, str):
                sname = state
            text = self._NEG_STATE_ID_TO_TEXT.get(sid, "")
            if not text and sname:
                low = sname.lower()
                for kw, mapped in self._NEG_LIST_KEYWORDS:
                    if kw in low:
                        text = mapped
                        break
            return text, f"id={sid!r} name={sname!r}"

        def walk(obj):
            if isinstance(obj, dict):
                vac = obj.get("vacancy")
                vid = ""
                title = ""
                if isinstance(vac, dict):
                    vid = str(vac.get("id") or vac.get("vacancyId") or "")
                    title = vac.get("name") or vac.get("title") or ""
                if not vid:
                    raw = obj.get("vacancyId") or obj.get("vacancy_id")
                    if raw:
                        vid = str(raw)
                if vid.isdigit():
                    text, raw_state = _status_text(obj)
                    if not sample_logged[0]:
                        logging.info(
                            f"[NegList:item] vid={vid} title={title[:40]!r} "
                            f"{raw_state} keys={list(obj.keys())[:14]}"
                        )
                        sample_logged[0] = True
                    if vid not in found or (text and not found[vid]["hh_status"]):
                        found[vid] = {
                            "vacancy_id": vid, "hh_status": text,
                            "title": title[:80], "company": "",
                        }
                for v in obj.values():
                    walk(v)
            elif isinstance(obj, list):
                for v in obj:
                    walk(v)

        for _url, data in captured:
            walk(data)

        results = [it for it in found.values()]
        if progress_callback and results:
            for i, it in enumerate(results, 1):
                progress_callback(i, len(results), it.get("title") or it["vacancy_id"])
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

    def _parse_negotiations_list(self, html: str) -> list[dict]:
        """Извлекает из HTML страницы «Отклики» список {vacancy_id, hh_status, title}."""
        soup = BeautifulSoup(html, "html.parser")
        items: list[dict] = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=re.compile(r"/vacancy/(\d+)")):
            m = re.search(r"/vacancy/(\d+)", a.get("href", ""))
            if not m:
                continue
            vid = m.group(1)
            if vid in seen:
                continue

            title = a.get_text(" ", strip=True)
            # Поднимаемся к карточке отклика и читаем её текст для статуса.
            card = a
            card_text = ""
            for _ in range(6):
                card = card.parent
                if card is None:
                    break
                txt = card.get_text(" ", strip=True)
                # Карточка одного отклика: разумный объём текста и есть статусное слово.
                if 20 < len(txt) < 1200:
                    card_text = txt
                    low = txt.lower()
                    if any(k in low for k, _ in self._NEG_LIST_KEYWORDS):
                        break

            low = card_text.lower()
            status = ""
            for keyword, mapped in self._NEG_LIST_KEYWORDS:
                if keyword in low:
                    status = mapped
                    break

            seen.add(vid)
            items.append({
                "vacancy_id": vid,
                "hh_status": status,
                "title": title[:80],
                "company": "",
            })
            # Сырой текст карточки — для доточки маппинга по реальным данным.
            logging.info(
                f"[NegList:{vid}] «{title[:40]}» статус=«{status or '?'}» "
                f"текст={card_text[:160]!r}"
            )

        return items

    def _fetch_via_vacancy_pages(
        self, page, vacancy_ids: list[str],
        progress_callback: Callable | None = None,
    ) -> list[dict]:
        """Фолбэк: поштучный обход страниц вакансий из CRM (медленно)."""
        results: list[dict] = []
        total = len(vacancy_ids)
        for idx, vid in enumerate(vacancy_ids, 1):
            url = f"https://hh.ru/vacancy/{vid}"
            logging.info(f"[Sync] {idx}/{total} → {url}")
            if progress_callback:
                progress_callback(idx, total, f"загружаю {vid}…")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                try:
                    page.wait_for_selector(
                        "[data-qa*='response'],[data-qa*='status'],[data-qa*='vacancy-title']",
                        timeout=5000,
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
