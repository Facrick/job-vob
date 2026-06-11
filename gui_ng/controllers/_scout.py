"""Scout/CRM вкладка: таблица вакансий, воронка, поиск."""
import asyncio
import logging

from nicegui import run, ui

from core.matching import compute_match_score
from core.search_service import SearchService
from gui_ng.controllers._helpers import _q
from gui_ng.theme import STATUS_STYLE, match_color


class _ScoutMixin:
    """Методы вкладки CRM: таблица вакансий, воронка, поиск."""

    # Порядок статусов для сортировки (чем выше — тем «активнее»)
    _STATUS_SORT_ORDER = {
        "offer": 6, "interview": 5, "applied": 4,
        "processed": 3, "discovered": 2, "rejected": 1,
    }

    def _row_dict(self, v: dict) -> dict:
        score = v.get("match_score")
        label, scolor = STATUS_STYLE.get(
            v.get("status", ""), (v.get("status", "") or "—", "#9aa0b4")
        )
        return {
            "id": v["id"],
            "match": "—" if score is None else f"{int(score)}%",
            # Числовые поля для сортировки: -1 означает «нет данных» → в конец
            "match_num": int(score) if score is not None else -1,
            "match_color": match_color(score),
            "company": v.get("company", ""),
            "title": v.get("title", ""),
            "salary": self._format_salary(v.get("salary_min"), v.get("salary_max")),
            "salary_num": int(v["salary_min"]) if v.get("salary_min") else -1,
            "salary_color": self._salary_color(v.get("salary_min"), v.get("salary_max")),
            "status": label,
            "status_color": scolor,
            "status_num": self._STATUS_SORT_ORDER.get(v.get("status", ""), 0),
        }

    def refresh_table_data(self):
        if "table" not in self.el:
            return
        status_filter = self.el["status_filter"].value or "all"
        vacancies = self.repo.get_vacancies_filtered(status_filter)
        all_rows = [self._row_dict(v) for v in vacancies]
        self._crm_all_rows = all_rows
        self.el["table"].rows = self._filter_crm_rows(all_rows)
        self.el["table"].update()
        self._update_funnel_counters()
        self._render_funnel()
        self.refresh_letter_vacancy_select()

    def _filter_crm_rows(self, rows: list[dict]) -> list[dict]:
        """Фильтрует строки таблицы по тексту из поля crm_search."""
        query = (self.el.get("crm_search") and self.el["crm_search"].value or "").strip().lower()
        if not query:
            return rows
        return [
            r for r in rows
            if query in (r.get("title") or "").lower()
            or query in (r.get("company") or "").lower()
        ]

    def handle_crm_search(self) -> None:
        """Вызывается при вводе в поле поиска CRM — фильтрует строки без запроса к БД."""
        if "table" not in self.el:
            return
        all_rows = getattr(self, "_crm_all_rows", None)
        if all_rows is None:
            # Кеш ещё не заполнен — делаем полную перезагрузку
            self.refresh_table_data()
            return
        self.el["table"].rows = self._filter_crm_rows(all_rows)
        self.el["table"].update()

    def _update_funnel_counters(self):
        all_vac = self.repo.get_vacancies_filtered("all")
        counts: dict[str, int] = {}
        for v in all_vac:
            counts[v.get("status", "")] = counts.get(v.get("status", ""), 0) + 1

        metrics = self.el.get("funnel_metrics")
        if not metrics:
            return
        active = sum(counts.get(k, 0) for k in ("processed", "applied", "interview"))
        values = {
            "total":     len(all_vac),
            "new":       counts.get("discovered", 0),
            "active":    active,
            "interview": counts.get("interview", 0),
            "offer":     counts.get("offer", 0),
        }
        for key, label in values.items():
            lbl = metrics.get(key)
            if lbl is not None:
                lbl.set_text(str(label))

    def on_row_click(self, e):
        try:
            row = e.args[1]
        except (IndexError, TypeError):
            return
        self.select_vacancy(row.get("id"))

    def select_vacancy(self, vid: str):
        from core.utils import vacancy_desc_to_html
        self.selected_vacancy_id = vid
        v = self.repo.get_vacancy_by_id(vid)
        if not v:
            return
        salary = self._format_salary(v.get("salary_min"), v.get("salary_max"))
        score = v.get("match_score")
        match_part = f"   ·   Match {int(score)}%" if score is not None else ""
        self.el["detail_title"].set_text(v.get("title", "Без названия"))
        self.el["detail_meta"].set_text(
            f"{v.get('company', 'Не указана')}   ·   {salary}{match_part}"
        )
        self.el["detail_meta"].style(
            f"color:{self._salary_color(v.get('salary_min'), v.get('salary_max'))}"
        )
        self.el["detail_skills"].set_text(v.get("skills") or "Не указаны")
        desc = v.get("description") or ""
        self.el["detail_description"].set_content(
            vacancy_desc_to_html(desc) if desc else "<em>Описание отсутствует.</em>"
        )
        self.el["detail_analysis"].set_content(
            "_Нажмите «Анализ ИИ», чтобы получить разбор вакансии._"
        )
        self.el["detail_gaps"].clear()
        self._suppress_status_change = True
        self.el["detail_status"].set_value(v.get("status", "discovered"))
        self._suppress_status_change = False
        self.el["detail_status"].set_visibility(True)
        self.el["detail_notes"].set_value(v.get("notes") or "")
        self.el["detail_hr_name"].set_value(v.get("hr_name") or "")
        self.el["detail_contacts"].set_value(v.get("contacts") or "")
        self.el["detail_interview_date"].set_value(v.get("interview_date") or "")
        for key in ("btn_generate", "btn_analyze", "btn_open_url", "btn_delete_vacancy"):
            self.el[key].set_visibility(True)

        _APPLIED_STATUSES = {"applied", "interview", "offer", "rejected"}
        already_applied = v.get("status", "") in _APPLIED_STATUSES
        btn = self.el["btn_auto_apply"]
        if already_applied:
            btn.disable()
            btn.tooltip("Отклик уже отправлен на эту вакансию")
        else:
            btn.enable()
            btn.tooltip("")

        label = f"{v.get('company', '')} — {v.get('title', '')}"
        self.el["letter_vacancy_label"].set_text(label)
        self.el["letter_vacancy_label"].classes(remove="italic")
        self.el["interview_vacancy_label"].set_text(f"Вакансия: {label}")

        existing = self.repo.get_cover_letter(vid)
        self.el["text_letter"].set_value(existing.get("letter_text", "") if existing else "")
        self.el["text_recs"].set_value(existing.get("recommendations", "") if existing else "")

        saved_chat = self.repo.get_mock_interview(vid)
        self.mock_chat_history = saved_chat or []
        self._render_mock_chat()

    # ── Bulk-действия ────────────────────────────────────────────────────────

    def _get_selected_ids(self) -> list[str]:
        """Список id строк, отмеченных чекбоксами в таблице."""
        return [row["id"] for row in (self.el["table"].selected or [])]

    def handle_bulk_selection_change(self, e=None) -> None:
        """Вызывается при изменении выделения в таблице.
        Читает table.selected напрямую — не зависит от формата e.args.
        """
        count = len(self.el["table"].selected or [])
        bar = self.el["bulk_bar"]
        if count:
            self.el["bulk_count_label"].set_text(f"Выбрано: {count}")
            bar.set_visibility(True)
        else:
            bar.set_visibility(False)

    def handle_bulk_deselect(self) -> None:
        self.el["table"].selected.clear()
        self.el["table"].update()
        self.el["bulk_bar"].set_visibility(False)

    def handle_bulk_status(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            return
        new_status = self.el["bulk_status_select"].value
        if not new_status:
            ui.notify("Выберите новый статус.", type="warning")
            return
        for vid in ids:
            self.repo.update_status(vid, new_status)
        _STATUS_LABEL = {
            "discovered": "Новая", "processed": "Письмо готово",
            "applied": "Отклик отправлен", "interview": "Собеседование",
            "offer": "Оффер!", "rejected": "Отказ",
        }
        label = _STATUS_LABEL.get(new_status, new_status)
        ui.notify(f"{len(ids)} вакансий → «{label}»", type="positive", icon="done_all")
        self.handle_bulk_deselect()
        self.refresh_table_data()

    def handle_bulk_delete(self) -> None:
        ids = self._get_selected_ids()
        if not ids:
            return
        count = len(ids)

        def _do_delete():
            for vid in ids:
                self.repo.delete_vacancy(vid)
            if self.selected_vacancy_id in ids:
                self.selected_vacancy_id = None
                self.el["detail_title"].set_text("Вакансия не выбрана")
                self.el["detail_meta"].set_text(
                    "Кликните строку в таблице слева, чтобы увидеть подробности."
                )
                self.el["detail_status"].set_visibility(False)
                for key in ("btn_generate", "btn_analyze", "btn_open_url", "btn_delete_vacancy"):
                    self.el[key].set_visibility(False)
            ui.notify(f"Удалено {count} вакансий.", type="positive", icon="delete")
            dlg.close()
            self.handle_bulk_deselect()
            self.refresh_table_data()

        with ui.dialog() as dlg, ui.card().style(
            "background:#18181b;border:1px solid #27272a;min-width:400px"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("warning", color="negative")
                ui.label(f"Удалить {count} вакансий?").classes(
                    "text-base font-semibold"
                ).style("color:#fafafa")
            ui.label(
                "Будут удалены все связанные данные: письма, история интервью."
            ).classes("text-xs").style("color:#71717a")
            with ui.row().classes("justify-end gap-2 w-full"):
                ui.button("Отмена", on_click=dlg.close).props("flat no-caps")
                ui.button(
                    "Удалить всё", on_click=_do_delete, icon="delete"
                ).props("no-caps color=negative")
        dlg.open()

    # ── Одиночное удаление ────────────────────────────────────────────────────

    def handle_delete_vacancy(self) -> None:
        """Удалить текущую выбранную вакансию с подтверждением."""
        vid = getattr(self, "selected_vacancy_id", None)
        if not vid:
            return
        v = self.repo.get_vacancy_by_id(vid)
        if not v:
            return
        title = v.get("title", "Без названия")
        company = v.get("company", "")
        label = f"{company} — {title}" if company else title

        def _do_delete():
            self.repo.delete_vacancy(vid)
            self.selected_vacancy_id = None
            # Скрываем панель деталей
            self.el["detail_title"].set_text("Вакансия не выбрана")
            self.el["detail_meta"].set_text(
                "Кликните строку в таблице слева, чтобы увидеть подробности."
            )
            self.el["detail_meta"].style("")
            self.el["detail_status"].set_visibility(False)
            for key in ("btn_generate", "btn_analyze", "btn_open_url", "btn_delete_vacancy"):
                self.el[key].set_visibility(False)
            self.refresh_table_data()
            ui.notify(f"Вакансия «{title}» удалена.", type="positive", icon="delete")
            dlg.close()

        with ui.dialog() as dlg, ui.card().style(
            "background:#18181b;border:1px solid #27272a;min-width:400px"
        ):
            with ui.row().classes("items-center gap-2"):
                ui.icon("warning", color="negative")
                ui.label("Удалить вакансию?").classes("text-base font-semibold").style(
                    "color:#fafafa"
                )
            ui.label(label).classes("text-sm").style("color:#a1a1aa")
            ui.label(
                "Будут удалены все связанные данные: письма, история интервью."
            ).classes("text-xs").style("color:#71717a")
            with ui.row().classes("justify-end gap-2 w-full"):
                ui.button("Отмена", on_click=dlg.close).props("flat no-caps")
                ui.button(
                    "Удалить", on_click=_do_delete, icon="delete"
                ).props("no-caps color=negative")
        dlg.open()

    def toggle_filters(self):
        box = self.el["filters_row"]
        box.set_visibility(not box.visible)

    def _render_funnel(self):
        box = self.el.get("funnel_box")
        if box is None:
            return
        vac = self.repo.get_vacancies_filtered("all")
        total = len(vac)
        box.clear()
        if total == 0:
            with box:
                ui.label("Нет данных — соберите вакансии на вкладке CRM.").classes(
                    "italic vob-muted"
                )
            return
        c: dict[str, int] = {}
        for v in vac:
            c[v.get("status", "")] = c.get(v.get("status", ""), 0) + 1

        n_discovered = c.get("discovered", 0)
        n_processed  = c.get("processed", 0)
        n_applied    = c.get("applied", 0)
        n_interview  = c.get("interview", 0)
        n_offer      = c.get("offer", 0)
        n_rejected   = c.get("rejected", 0)

        reached_applied   = n_applied + n_interview + n_offer
        reached_interview = n_interview + n_offer

        metrics = [
            ("Всего",         total,       "#42a5f5"),
            ("Откликнулся",   n_applied,   "#ff8f00"),
            ("Собеседования", n_interview, "#ab47bc"),
            ("Офферы",        n_offer,     "#66bb6a"),
            ("Отказы",        n_rejected,  "#ef5350"),
        ]
        with box:
            with ui.row().classes("gap-3 flex-wrap"):
                for label, value, color in metrics:
                    if value == 0 and label not in ("Всего",):
                        continue
                    with ui.card().style(
                        f"background-color:{color}1f;padding:10px 14px"
                    ).props("flat"):
                        ui.label(str(value)).style(
                            f"font-size:22px;font-weight:700;color:{color}"
                        )
                        ui.label(label).classes("text-xs vob-muted")
            ui.separator()
            stages = [
                ("Новые",            n_discovered, "#42a5f5"),
                ("Письмо готово",    n_processed,  "#5c6bc0"),
                ("Отклик отправлен", n_applied,    "#ff8f00"),
                ("Собеседование",    n_interview,  "#ab47bc"),
                ("Оффер",            n_offer,      "#66bb6a"),
                ("Отказ",            n_rejected,   "#ef5350"),
            ]
            for label, count, color in stages:
                ratio = count / total if total else 0
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("w-full justify-between"):
                        ui.label(label).classes("font-medium")
                        ui.label(
                            f"{count}  ·  {round(ratio * 100)}% от всех"
                        ).classes("text-xs vob-muted")
                    ui.linear_progress(value=ratio, show_value=False).props(
                        f"color={_q(color)}"
                    )
            if reached_applied:
                resp = round(reached_interview / reached_applied * 100)
                off  = round(n_offer / reached_interview * 100) if reached_interview else 0
                ui.label(
                    f"Отклик → собеседование: {resp}%      "
                    f"Собеседование → оффер: {off}%"
                ).style("color:#7986cb;font-weight:500;font-size:12px")

    async def handle_search(self):
        """Запускает поиск. Если есть непросмотренные «Новые» вакансии — спрашивает подтверждение."""
        n_discovered = len(self.repo.get_vacancies_filtered("discovered"))
        if n_discovered:
            confirmed = asyncio.Event()
            cancelled = asyncio.Event()

            with ui.dialog() as dlg, ui.card().style(
                "background:#18181b;border:1px solid #27272a;min-width:420px"
            ):
                with ui.row().classes("items-center gap-2"):
                    ui.icon("warning_amber", color="warning")
                    ui.label("Удалить непросмотренные вакансии?").classes(
                        "text-base font-semibold"
                    ).style("color:#fafafa")
                ui.label(
                    f"В CRM есть {n_discovered} вакансий со статусом «Новая»."
                ).classes("text-sm").style("color:#a1a1aa")
                ui.label(
                    "Новый поиск удалит их и заменит свежими результатами. "
                    "Вакансии в других статусах (письмо, отклик, собеседование…) "
                    "останутся нетронутыми."
                ).classes("text-xs").style("color:#71717a")
                with ui.row().classes("justify-end gap-2 w-full"):
                    def _cancel():
                        cancelled.set()
                        dlg.close()

                    def _confirm():
                        confirmed.set()
                        dlg.close()

                    ui.button("Отмена", on_click=_cancel).props("flat no-caps")
                    ui.button(
                        "Продолжить", icon="search", on_click=_confirm
                    ).props("no-caps")
            dlg.open()
            # Ждём действия пользователя
            await asyncio.wait(
                [asyncio.ensure_future(confirmed.wait()),
                 asyncio.ensure_future(cancelled.wait())],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if cancelled.is_set():
                return

        await self._do_search()

    async def _do_search(self):
        """Фактический запуск поиска вакансий на hh.ru."""
        keyword = (self.el["input_keyword"].value or "").strip() or "QA Engineer"
        period = self.el["combo_period"].value or "7"
        exp = self.el["combo_exp"].value or "between1And3"
        area = self.el["combo_area"].value or "113"
        sched_val = self.el["combo_schedule"].value
        schedule = sched_val if sched_val is not None else ""
        expand = bool(self.el["toggle_expand"].value)

        progress = self.el["search_progress"]
        status = self.el["search_status"]
        progress.set_visibility(True)
        status.set_visibility(True)
        status.set_text("Запускаю поиск и открываю hh.ru...")
        self.el["btn_search"].disable()

        loop = asyncio.get_running_loop()

        def on_progress(idx, total, label=""):
            def upd():
                progress.set_value((idx / total) if total else None)
                status.set_text(f"Обработка {idx}/{total}: {label}")
            loop.call_soon_threadsafe(upd)

        def on_vacancy(v: dict):
            v["match_score"] = compute_match_score(self._cached_resume, v)
            v.setdefault("status", "discovered")
            self.repo.save_vacancies([v])

            def upd():
                self.el["table"].add_row(self._row_dict(v))
                self._update_funnel_counters()
            loop.call_soon_threadsafe(upd)

        def job():
            self.repo.clear_discovered_vacancies()
            self._cached_resume = self._safe_resume_text()
            SearchService().search(
                text=keyword, expand=expand,
                period=int(period), area=int(area), experience=exp,
                schedule=schedule, page_limit=3,
                progress_callback=on_progress, on_vacancy=on_vacancy,
            )

        try:
            # Сбрасываем текстовый фильтр, чтобы новые вакансии не скрывались
            if "crm_search" in self.el:
                self.el["crm_search"].set_value("")
            self._crm_all_rows = None

            kept = [
                v for v in self.repo.get_vacancies_filtered("all")
                if v.get("status") != "discovered"
            ]
            self.el["table"].rows = [self._row_dict(v) for v in kept]
            self.el["table"].update()
            logging.info("🧹 Удаляю необработанные вакансии (статус «Новая»)…")
            await run.io_bound(job)
            logging.info("💾 Поиск завершён.")
            self.refresh_table_data()
        except Exception as ex:
            logging.error(f"[BG] Поиск завершился с ошибкой: {ex}")
            self._show_error(str(ex))
        finally:
            progress.set_visibility(False)
            status.set_visibility(False)
            self.el["btn_search"].enable()
