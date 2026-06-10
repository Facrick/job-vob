"""Интеграция с hh.ru: авторизация и синхронизация статусов."""
import asyncio
import logging

from nicegui import run, ui

from core.hh_sync import sync_negotiations
from core.parser import HHParser


class _HHMixin:
    """Методы проверки авторизации на hh.ru и синхронизации статусов откликов."""

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
        badge = self.el["hh_auth_badge"]
        btn   = self.el["btn_hh_login"]
        if logged_in:
            badge.set_text("⬤  hh.ru  авторизован")
            badge.style(self._AUTH_STYLE_ON)
            btn.set_visibility(False)
        else:
            badge.set_text("⬤  hh.ru  не авторизован")
            badge.style(self._AUTH_STYLE_OFF)
            btn.set_visibility(True)

    async def _check_hh_auth_async(self) -> None:
        self.el["hh_auth_badge"].set_text("⬤  hh.ru  проверка…")
        self.el["hh_auth_badge"].style(self._AUTH_STYLE_WAIT)
        try:
            logged_in = await run.io_bound(HHParser().check_auth_status)
            self._set_hh_auth_ui(logged_in)
            logging.info(f"🔐 Статус hh.ru: {'авторизован' if logged_in else 'не авторизован'}")
        except Exception as ex:
            logging.warning(f"[Auth] Не удалось проверить статус hh.ru: {ex}")
            self.el["hh_auth_badge"].set_text("⬤  hh.ru  ошибка проверки")
            self.el["hh_auth_badge"].style(self._AUTH_STYLE_WAIT)

    def recheck_hh_auth(self) -> None:
        """Ручной перезапуск проверки авторизации (кнопка ↺)."""
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
                self.el["btn_hh_login"].disable()
                self.el["hh_auth_badge"].set_text("⬤  hh.ru  выполняется вход…")
                self.el["hh_auth_badge"].style(self._AUTH_STYLE_WAIT)
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
                self._show_error(f"Ошибка входа: {ex}")
                self.el["btn_hh_login"].enable()
        ui.timer(0.01, _login_and_recheck, once=True)
