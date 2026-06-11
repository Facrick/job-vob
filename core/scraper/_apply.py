"""Автоотклик на вакансию через Playwright — миксин для HHParser."""
import logging
import time


class _ApplyMixin:
    """Метод автоматической отправки отклика с сопроводительным письмом."""

    def _diag_apply_form(self, page, vacancy_id: str) -> None:
        """Лог состояния формы отклика, когда поле письма не нашлось."""
        import re as _re
        from bs4 import BeautifulSoup
        logging.error("❌ [Apply:diag] поле письма не найдено — собираю структуру формы")
        try:
            logging.info(f"[Apply:diag] url={page.url}")
        except Exception:
            pass

        # Фреймы: форма отклика может быть в iframe (тогда её нет в page.content()).
        try:
            frames = page.frames
            finfo = [(f.url[:70]) for f in frames if f.url and "about:blank" not in f.url]
            logging.info(f"[Apply:diag] frames={len(frames)} urls={finfo[:6]}")
            # textarea внутри каждого фрейма.
            for i, f in enumerate(frames):
                try:
                    n = f.locator("textarea").count()
                    ce = f.locator("[contenteditable='true']").count()
                    if n or ce:
                        logging.info(f"[Apply:diag] frame#{i} textarea={n} contenteditable={ce} url={f.url[:60]}")
                except Exception:
                    continue
        except Exception as exc:
            logging.info(f"[Apply:diag] frames: {exc}")

        try:
            html = page.content()
            soup = BeautifulSoup(html, "html.parser")
            tas = [{"data-qa": ta.get("data-qa", ""), "name": ta.get("name", ""),
                    "ph": (ta.get("placeholder", "") or "")[:30]}
                   for ta in soup.find_all("textarea")]
            logging.info(f"[Apply:diag] textareas(main)={tas or '—'}")

            low = soup.get_text(" ", strip=True).lower()
            logging.info(
                f"[Apply:diag] есть_вопросы={'vacancy-response-question' in html} "
                f"перс_данные={'персональных данных' in low or 'политикой конфиденц' in low} "
                f"выбор_резюме={'выберите резюме' in low or 'каким резюме' in low} "
                f"vpncheck={'vpncheeck' in (getattr(page, 'url', '') or '')}"
            )

            dqa = {}
            for el in soup.find_all(attrs={"data-qa": True}):
                raw = el.get("data-qa") or ""
                parts = raw.split()
                key = parts[0] if parts else ""
                if key and _re.search(
                    r"response|letter|popup|dialog|question|submit|resume|consent", key, _re.I
                ):
                    dqa[key] = dqa.get(key, 0) + 1
            logging.info(
                f"[Apply:diag] data-qa(form)={sorted(dqa.items(), key=lambda kv: -kv[1])[:15]}"
            )
        except Exception as exc:
            logging.warning(f"[Apply:diag] разбор HTML не удался: {exc}")

    def auto_apply(self, vacancy_id: str, letter_text: str) -> tuple[bool, str]:
        from playwright.sync_api import sync_playwright
        import random

        with sync_playwright() as p:
            logging.info(f"📨 Отправляю отклик на вакансию {vacancy_id}...")

            if not self._check_logged_in(p):
                logging.info("🔒 Сессия hh.ru не найдена — требуется авторизация.")
                if not self._login_in_browser(p):
                    return False, (
                        "Авторизация на hh.ru не выполнена. "
                        "Повторите попытку и войдите в аккаунт в открывшемся окне браузера."
                    )

            context = p.chromium.launch_persistent_context(
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
            # Стелс против анти-бота hh.ru (/vpncheeck).
            try:
                context.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    "window.chrome={runtime:{}};"
                    "Object.defineProperty(navigator,'languages',{get:()=>['ru-RU','ru']});"
                    "Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});"
                )
            except Exception:
                pass
            page = context.new_page()

            def first_visible(selectors, timeout_ms=5000, scope=None):
                """Первый видимый элемент из списка селекторов (с ожиданием).

                scope — page или конкретный frame (форма может быть в iframe).
                """
                sc = scope or page
                deadline = time.time() + timeout_ms / 1000
                while time.time() < deadline:
                    for sel in selectors:
                        try:
                            loc = sc.locator(sel).first
                            if loc.count() and loc.is_visible():
                                return loc
                        except Exception:
                            continue
                    page.wait_for_timeout(250)
                return None

            def find_in_any_scope(selectors, timeout_ms=6000):
                """Ищет элемент на главной странице, затем во всех фреймах.

                Возвращает (locator, scope) — scope нужен, чтобы дальше искать
                кнопку отправки в том же документе (iframe формы отклика)."""
                loc = first_visible(selectors, timeout_ms=timeout_ms)
                if loc:
                    return loc, page
                for fr in list(page.frames):
                    if fr == page.main_frame:
                        continue
                    loc = first_visible(selectors, timeout_ms=1500, scope=fr)
                    if loc:
                        logging.info(f"✉️ Поле найдено во фрейме: {fr.url[:60]}")
                        return loc, fr
                return None, page

            try:
                url = f"https://hh.ru/vacancy/{vacancy_id}"
                page.goto(url, timeout=40000, wait_until="domcontentloaded")
                # Пережидаем анти-бот hh.ru, если перебросило на /vpncheeck.
                try:
                    self._wait_through_vpncheck(page, url)
                except Exception:
                    pass
                page.wait_for_timeout(2000)

                apply_btn = first_visible([
                    '[data-qa="vacancy-response-link-top"]',
                    '[data-qa="vacancy-response-link-bottom"]',
                    'button:has-text("Откликнуться")',
                    'a:has-text("Откликнуться")',
                    ':text("Откликнуться")',
                ], timeout_ms=15000)
                if not apply_btn:
                    return False, (
                        "Кнопка «Откликнуться» не найдена. Вероятные причины: "
                        "отклик уже отправлен ранее, вакансия закрыта, "
                        "или требуется повторная авторизация на hh.ru."
                    )

                logging.info("🖱 Нажимаю «Откликнуться»...")
                apply_btn.click()
                page.wait_for_timeout(2500)

                # hh.ru после клика может: открыть попап, увести на отдельную
                # страницу отклика, показать скрининг-вопросы/согласие. Ждём, пока
                # появится поле письма ИЛИ сменится URL.
                page.wait_for_timeout(1500)

                toggle, _ = find_in_any_scope([
                    '[data-qa="vacancy-response-letter-toggle"]',
                    '[data-qa*="letter-toggle"]',
                    'button:has-text("Сопроводительное письмо")',
                    'button:has-text("сопроводительное")',
                    'text=Добавить сопроводительное',
                    ':text("Сопроводительное письмо")',
                ], timeout_ms=3000)
                if toggle:
                    logging.info("✉️ Раскрываю поле сопроводительного письма...")
                    try:
                        toggle.click()
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)

                # Ищем поле письма на странице И во всех фреймах (форма отклика
                # hh.ru может быть в iframe). scope запоминаем для кнопки отправки.
                textarea, scope = find_in_any_scope([
                    'textarea[data-qa="vacancy-response-popup-form-letter-input"]',
                    'textarea[data-qa="vacancy-response-letter-input"]',
                    'textarea[data-qa*="letter"]',
                    'textarea[name="text"]',
                    '.vacancy-response-popup textarea',
                    'div[role="dialog"] textarea',
                    'textarea',
                    '[contenteditable="true"]',
                ], timeout_ms=8000)
                if not textarea:
                    self._diag_apply_form(page, vacancy_id)
                    return False, (
                        "Не удалось прикрепить сопроводительное письмо: поле ввода "
                        "не найдено. Похоже, hh.ru изменил форму отклика "
                        "(скрининг-вопросы / отдельная страница). Подробности — в логах."
                    )

                logging.info("⌨️ Вставляю текст сопроводительного письма...")
                text = letter_text[:3000]
                try:
                    textarea.fill(text)
                except Exception:
                    # contenteditable / rich-редактор: fill не работает — печатаем.
                    try:
                        textarea.click()
                        textarea.type(text, delay=2)
                    except Exception:
                        pass
                page.wait_for_timeout(1000)
                try:
                    filled = (textarea.input_value() or "").strip()
                except Exception:
                    filled = (textarea.inner_text() or "").strip()
                if not filled:
                    return False, "Письмо не вставилось в поле. Отклик не отправлен."

                submit_btn = first_visible([
                    'button[data-qa="vacancy-response-submit-popup"]',
                    '[data-qa="vacancy-response-letter-submit"]',
                    'button[data-qa="vacancy-response-submit"]',
                    '[data-qa*="response-submit"]',
                    '.vacancy-response-popup button[type="submit"]',
                    'div[role="dialog"] button:has-text("Откликнуться")',
                    'div[role="dialog"] button:has-text("Отправить")',
                ], timeout_ms=4000, scope=scope)
                if not submit_btn:
                    return False, "Не найдена кнопка отправки отклика."

                logging.info("📤 Отправляю отклик вместе с письмом...")
                submit_btn.click()
                page.wait_for_timeout(3000)
                return True, "Автоотклик с сопроводительным письмом отправлен!"

            except Exception as e:
                logging.error(f"[Auto-Apply] Ошибка: {e}")
                return False, f"Сбой автоматизации: {str(e)}"
            finally:
                context.close()
