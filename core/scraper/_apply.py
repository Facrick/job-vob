"""Автоотклик на вакансию через Playwright — миксин для HHParser."""
import logging
import time


class _ApplyMixin:
    """Метод автоматической отправки отклика с сопроводительным письмом."""

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
            )
            page = context.new_page()

            def first_visible(selectors, timeout_ms=5000):
                """Первый видимый элемент из списка селекторов (с ожиданием)."""
                deadline = time.time() + timeout_ms / 1000
                while time.time() < deadline:
                    for sel in selectors:
                        loc = page.locator(sel).first
                        try:
                            if loc.count() and loc.is_visible():
                                return loc
                        except Exception:
                            continue
                    page.wait_for_timeout(250)
                return None

            try:
                page.goto(
                    f"https://hh.ru/vacancy/{vacancy_id}",
                    timeout=40000,
                    wait_until="domcontentloaded",
                )
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

                toggle = first_visible([
                    '[data-qa="vacancy-response-letter-toggle"]',
                    'button:has-text("Сопроводительное письмо")',
                    'text=Добавить сопроводительное',
                ], timeout_ms=2500)
                if toggle:
                    logging.info("✉️ Раскрываю поле сопроводительного письма...")
                    toggle.click()
                    page.wait_for_timeout(1000)

                textarea = first_visible([
                    'textarea[data-qa="vacancy-response-popup-form-letter-input"]',
                    'textarea[data-qa="vacancy-response-letter-input"]',
                    'textarea[name="text"]',
                    '.vacancy-response-popup textarea',
                ], timeout_ms=6000)
                if not textarea:
                    logging.error("❌ Поле письма не найдено — отклик НЕ отправлен.")
                    return False, (
                        "Не удалось прикрепить сопроводительное письмо: поле ввода "
                        "не найдено. Отклик не отправлен (чтобы не уйти без письма)."
                    )

                logging.info("⌨️ Вставляю текст сопроводительного письма...")
                textarea.fill(letter_text[:3000])
                page.wait_for_timeout(1000)
                if not (textarea.input_value() or "").strip():
                    return False, "Письмо не вставилось в поле. Отклик не отправлен."

                submit_btn = first_visible([
                    'button[data-qa="vacancy-response-submit-popup"]',
                    '[data-qa="vacancy-response-letter-submit"]',
                    'button[data-qa="vacancy-response-submit"]',
                    '.vacancy-response-popup button[type="submit"]',
                ], timeout_ms=4000)
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
