"""Интеграция с hh.ru: авторизация и синхронизация статусов."""
import asyncio
import logging
import time

from nicegui import run, ui

from core.hh_sync import sync_negotiations
from core.parser import HHParser


class _HHMixin:
    """Методы проверки авторизации на hh.ru и синхронизации статусов откликов."""

    # Сколько секунд доверять закэшированному статусу авторизации.
    _HH_AUTH_TTL = 1800  # 30 минут

    async def get_hh_auth(self, *, force: bool = False) -> bool:
        """Единый источник статуса авторизации hh.ru для всех вкладок.

        Возвращает закэшированный результат, если он свежее _HH_AUTH_TTL,
        иначе поднимает headless-браузер и перепроверяет. Кэш общий (живёт на
        self), поэтому CRM и Аналитика всегда видят один и тот же статус.
        """
        fresh = (
            self._hh_auth_cached is not None
            and (time.monotonic() - self._hh_auth_checked_at) < self._HH_AUTH_TTL
        )
        if not force and fresh:
            return self._hh_auth_cached

        logged_in = await run.io_bound(HHParser().check_auth_status)
        self._hh_auth_cached = logged_in
        self._hh_auth_checked_at = time.monotonic()
        return logged_in

    def _mark_hh_authed(self) -> None:
        """Помечает сессию как авторизованную (после успешного ручного входа)."""
        self._hh_auth_cached = True
        self._hh_auth_checked_at = time.monotonic()

    # Стили для лампочки в CRM-баре (только цвет точки)
    _DOT_ON   = "color:#22c55e;font-size:14px;cursor:default"
    _DOT_OFF  = "color:#f87171;font-size:14px;cursor:default"
    _DOT_WAIT = "color:#71717a;font-size:14px;cursor:default"

    # Стили для текстового badge в Настройках
    _AUTH_STYLE_ON  = (
        "font-size:11px;font-weight:600;letter-spacing:.02em;"
        "padding:3px 8px;border-radius:6px;cursor:default;"
        "color:#22c55e;background:#14532d33;border:1px solid #22c55e66"
    )
    _AUTH_STYLE_OFF = (
        "font-size:11px;font-weight:600;letter-spacing:.02em;"
        "padding:3px 8px;border-radius:6px;cursor:default;"
        "color:#f87171;background:#7f1d1d33;border:1px solid #f8717166"
    )
    _AUTH_STYLE_WAIT = (
        "font-size:11px;font-weight:600;letter-spacing:.02em;"
        "padding:3px 8px;border-radius:6px;cursor:default;"
        "color:#71717a;background:#27272a;border:1px solid #3f3f46"
    )

    def _set_hh_auth_ui(self, logged_in: bool) -> None:
        # Лампочка в CRM-баре
        if "hh_auth_badge" in self.el:
            dot = self.el["hh_auth_badge"]
            dot.style(self._DOT_ON if logged_in else self._DOT_OFF)
        # Кнопка «Войти» в CRM-баре
        if "btn_hh_login" in self.el:
            self.el["btn_hh_login"].set_visibility(not logged_in)
        # Текстовый badge в Настройках
        if "hh_auth_badge_s" in self.el:
            badge_s = self.el["hh_auth_badge_s"]
            if logged_in:
                badge_s.set_text("⬤  авторизован")
                badge_s.style(self._AUTH_STYLE_ON)
            else:
                badge_s.set_text("⬤  не авторизован")
                badge_s.style(self._AUTH_STYLE_OFF)
        # Кнопка «Войти» в Настройках
        if "btn_hh_login_s" in self.el:
            self.el["btn_hh_login_s"].set_visibility(not logged_in)

    def _client_alive(self) -> bool:
        from nicegui.client import Client
        client_id = getattr(self, "_client_id", None)
        return client_id is None or client_id in Client.instances

    async def _check_hh_auth_async(self) -> None:
        if not self._client_alive():
            return

        # Ставим «проверка…» на оба badge
        if "hh_auth_badge" in self.el:
            self.el["hh_auth_badge"].style(self._DOT_WAIT)
        if "hh_auth_badge_s" in self.el:
            self.el["hh_auth_badge_s"].set_text("⬤  проверка…")
            self.el["hh_auth_badge_s"].style(self._AUTH_STYLE_WAIT)
        try:
            logged_in = await self.get_hh_auth(force=self._hh_auth_force_recheck)
            self._hh_auth_force_recheck = False
            if not self._client_alive():
                return
            self._set_hh_auth_ui(logged_in)
            logging.info(f"🔐 Статус hh.ru: {'авторизован' if logged_in else 'не авторизован'}")
        except Exception as ex:
            logging.warning(f"[Auth] Не удалось проверить статус hh.ru: {ex}")
            if not self._client_alive():
                return
            if "hh_auth_badge_s" in self.el:
                self.el["hh_auth_badge_s"].set_text("⬤  ошибка проверки")
                self.el["hh_auth_badge_s"].style(self._AUTH_STYLE_WAIT)

    def recheck_hh_auth(self) -> None:
        """Ручной перезапуск проверки авторизации (кнопка ↺) — игнорирует кэш."""
        self._hh_auth_force_recheck = True
        ui.timer(0.01, self._check_hh_auth_async, once=True)

    _AUTOSYNC_INTERVAL = 3600  # секунд (1 час)

    def handle_hh_sync(self) -> None:
        ui.timer(0.01, self._hh_sync_async, once=True)

    def handle_autosync_toggle(self, e) -> None:
        """Включает / выключает автосинхронизацию раз в час (вызов пользователем)."""
        if getattr(self, "_autosync_restoring", False):
            # Вызов из _restore_autosync_state — игнорируем, таймер уже создан там
            return
        self._set_autosync(bool(e.value), run_now=True)

    def _set_autosync(self, enabled: bool, *, run_now: bool = False) -> None:
        """Единственная точка управления таймером авто-синхронизации."""
        self.config.set("autosync_enabled", enabled)

        # Отменяем старый таймер если есть
        old_timer = getattr(self, "_autosync_timer", None)
        if old_timer is not None:
            old_timer.cancel()
            self._autosync_timer = None

        if enabled:
            if run_now:
                # Немедленный синк только при явном включении пользователем
                ui.timer(0.01, self._hh_sync_async, once=True)
            self._autosync_timer = ui.timer(
                self._AUTOSYNC_INTERVAL, self._hh_sync_async, once=False
            )
            logging.info(
                f"[AutoSync] Включена (интервал {self._AUTOSYNC_INTERVAL}s"
                f"{', немедленный запуск' if run_now else ', без немедленного запуска'})"
            )
            if run_now:
                ui.notify(
                    "Авто-синхронизация включена. Первый запрос выполняется сейчас.",
                    type="positive", icon="sync", timeout=3000,
                )
        else:
            logging.info("[AutoSync] Отключена")
            if run_now:
                ui.notify("Авто-синхронизация отключена.", type="info", timeout=2000)

    def _restore_autosync_state(self) -> None:
        """Восстанавливает таймер из конфига при старте. НЕ запускает немедленный синк."""
        enabled = bool(self.config.get("autosync_enabled"))
        if "toggle_autosync" in self.el:
            # Выставляем значение переключателя без срабатывания on_change
            self._autosync_restoring = True
            self.el["toggle_autosync"].set_value(enabled)
            self._autosync_restoring = False
        if enabled:
            # run_now=False — при старте не нужен немедленный синк
            self._set_autosync(enabled, run_now=False)
            logging.info("[AutoSync] Восстановлена из настроек")

    async def _hh_sync_async(self) -> None:
        btn = self.el["btn_hh_sync"]
        btn.disable()
        status_lbl = self.el["search_status"]
        progress   = self.el["search_progress"]

        # Проверяем все вакансии из CRM — пользователь мог откликнуться вручную
        # прямо на hh.ru, и в CRM статус остался «discovered»/«processed».
        # Исключаем только вакансии без id (не с hh.ru).
        candidates = [
            v for v in self.repo.get_vacancies_filtered("all")
            if v.get("id")
        ]
        if not candidates:
            ui.notify(
                "В CRM нет вакансий для проверки.",
                type="info",
            )
            btn.enable()
            return

        vacancy_ids = [v["id"] for v in candidates]
        total = len(vacancy_ids)
        status_lbl.set_text(f"Проверяю {total} вакансий на hh.ru…")
        status_lbl.set_visibility(True)
        progress.set_visibility(True)
        progress.set_value(0)

        try:
            loop = asyncio.get_running_loop()

            def on_progress(done, total_, label=""):
                def upd():
                    progress.set_value(done / total_ if total_ else None)
                    status_lbl.set_text(f"Проверяю {label}")
                loop.call_soon_threadsafe(upd)

            negotiations = await run.io_bound(
                HHParser().fetch_negotiations, vacancy_ids, on_progress
            )

            if not negotiations:
                ui.notify("hh.ru: переговоров не найдено (или парсинг не удался).",
                          type="warning")
                return

            status_lbl.set_text(f"Обновляю статусы в CRM ({len(negotiations)} переговоров)…")
            result = sync_negotiations(self.repo, negotiations)
            self.refresh_table_data()
            self._update_funnel_counters()
            self._set_hh_auth_ui(True)
            self._show_sync_result_dialog(result)

        except RuntimeError as ex:
            self._show_error(str(ex))
            self._set_hh_auth_ui(False)
        except Exception as ex:
            logging.error(f"[HH Sync] Ошибка: {ex}")
            self._show_error(f"Ошибка синхронизации: {ex}")
        finally:
            btn.enable()
            status_lbl.set_visibility(False)
            progress.set_visibility(False)

    def _show_sync_result_dialog(self, result) -> None:
        _STATUS_LABEL = {
            "discovered": "Новая",
            "processed":  "Письмо готово",
            "applied":    "Отклик отправлен",
            "interview":  "Собеседование",
            "offer":      "Оффер",
            "rejected":   "Отказ",
        }
        _STATUS_COLOR = {
            "applied":   "#60a5fa",
            "interview": "#a78bfa",
            "offer":     "#34d399",
            "rejected":  "#f87171",
        }

        with ui.dialog() as dlg, ui.card().classes("gap-3").style(
            "min-width:480px;max-width:640px;background:#18181b;border:1px solid #27272a"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("sync", color="primary")
                ui.label("Синхронизация с hh.ru завершена").classes(
                    "text-base font-semibold"
                ).style("color:#fafafa")

            for line in result.summary_lines():
                ui.label(line).classes("text-sm").style("color:#a1a1aa")

            if result.updated:
                ui.separator().style("opacity:.3")
                ui.label("Обновлённые вакансии:").classes("text-sm font-semibold").style(
                    "color:#e4e4e7"
                )
                with ui.scroll_area().style("max-height:280px;width:100%"):
                    for item in result.updated:
                        old_lbl = _STATUS_LABEL.get(item["old"], item["old"])
                        new_lbl = _STATUS_LABEL.get(item["new"], item["new"])
                        new_col = _STATUS_COLOR.get(item["new"], "#a1a1aa")
                        with ui.row().classes("items-center gap-2 w-full").style(
                            "padding:4px 0;border-bottom:1px solid #27272a"
                        ):
                            with ui.column().classes("gap-0 flex-grow"):
                                ui.label(item["title"] or item["vacancy_id"]).classes(
                                    "text-sm"
                                ).style("color:#e4e4e7")
                                if item["company"]:
                                    ui.label(item["company"]).classes("text-xs").style(
                                        "color:#71717a"
                                    )
                            ui.label(f"{old_lbl} →").classes("text-xs").style(
                                "color:#52525b;white-space:nowrap"
                            )
                            ui.label(new_lbl).classes("text-xs font-semibold").style(
                                f"color:{new_col};white-space:nowrap"
                            )

            with ui.row().classes("justify-end w-full"):
                ui.button("Закрыть", on_click=dlg.close).props("flat no-caps")

        dlg.open()

    def handle_hh_login(self) -> None:
        """Открывает браузер для ручного входа, затем перепроверяет статус."""
        async def _login_and_recheck():
            try:
                for key in ("btn_hh_login", "btn_hh_login_s"):
                    if key in self.el:
                        self.el[key].disable()
                if "hh_auth_badge_s" in self.el:
                    self.el["hh_auth_badge_s"].set_text("⬤  выполняется вход…")
                    self.el["hh_auth_badge_s"].style(self._AUTH_STYLE_WAIT)
                from playwright.sync_api import sync_playwright
                def _do_login():
                    with sync_playwright() as p:
                        return HHParser()._login_in_browser(p)
                success = await run.io_bound(_do_login)
                if success:
                    self._set_hh_auth_ui(True)
                    self._show_info("Авторизация hh.ru", "Вход выполнен успешно!")
                else:
                    self._set_hh_auth_ui(False)
                    self._show_error("Авторизация отменена или не завершена.")
            except Exception as ex:
                msg = str(ex)
                if "XServer" in msg or "DISPLAY" in msg or "headed browser" in msg or "headless" in msg.lower():
                    self._show_error(
                        "Вход через браузер недоступен в Docker-контейнере без X Server. "
                        "Войдите в hh.ru локально (запустив приложение на хосте) — "
                        "сессия сохранится в data/browser_user_data и подхватится контейнером."
                    )
                else:
                    self._show_error(f"Ошибка входа: {ex}")
                for key in ("btn_hh_login", "btn_hh_login_s"):
                    if key in self.el:
                        self.el[key].enable()
        ui.timer(0.01, _login_and_recheck, once=True)
