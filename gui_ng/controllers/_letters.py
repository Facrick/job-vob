"""Вкладка «Письма»: генерация, анализ, автоотклик, статус, заметки, резюме."""
import logging
import webbrowser

from nicegui import run, ui

from core.ai import LetterAnalyzer
from core.parser import HHParser
from core.utils import extract_salary_from_resume
from gui_ng.controllers._helpers import _q


class _LettersMixin:
    """Методы вкладки «Письма» + сопутствующие утилиты CRM."""

    async def handle_generation(self):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию в таблице.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        if not v:
            self._show_error("Вакансия не найдена в базе.")
            return
        vid = self.selected_vacancy_id
        self.el["btn_generate"].disable()
        try:
            resume_text = self.resume.extract_text()
            response = await run.io_bound(
                self.analyzer.generate_cover_letter,
                resume_text, v["title"], v["company"], v["description"],
            )
            letter = response.get("letter", "").strip()
            recs = "\n".join(f"• {r}" for r in response.get("recommendations", []))
            self.repo.save_cover_letter(vid, letter, recs)
            if v["status"] == "discovered":
                self.repo.update_status(vid, "processed")
            self.el["text_letter"].set_value(letter)
            self.el["text_recs"].set_value(recs)
            self.switch_to_tab(self.TAB_LETTERS)
            self.refresh_table_data()
        except Exception as ex:
            logging.error(f"[BG] {ex}")
            self._show_error(str(ex))
        finally:
            self.el["btn_generate"].enable()

    async def handle_analyze(self):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию в таблице.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        if not v:
            self._show_error("Вакансия не найдена в базе.")
            return
        self.el["detail_analysis"].set_content("⏳ ИИ анализирует вакансию...")
        self.el["btn_analyze"].disable()
        try:
            resume_text = self._safe_resume_text()
            data = await run.io_bound(
                self.analyzer.analyze_vacancy,
                resume_text, v["title"], v["company"], v["description"],
            )
            self.el["detail_analysis"].set_content(self._format_analysis(data))
            self._render_gap_links(data.get("gaps", []))
        except Exception as ex:
            logging.error(f"[BG] {ex}")
            self._show_error(str(ex))
        finally:
            self.el["btn_analyze"].enable()

    @staticmethod
    def _format_analysis(data: dict) -> str:
        def bullets(items):
            if isinstance(items, str):
                items = [items]
            return "\n".join(f"- {x}" for x in (items or [])) or "—"

        return (
            f"**Суть:** {data.get('summary', '—')}\n\n"
            f"**Ключевые требования:**\n{bullets(data.get('key_requirements'))}\n\n"
            f"**Стек:** {', '.join(data.get('stack', [])) or '—'}\n\n"
            f"**Соответствие резюме:** {data.get('match', '—')}\n\n"
            f"**На чём сделать акцент:**\n{bullets(data.get('highlights'))}\n\n"
            f"**Пробелы:**\n{bullets(data.get('gaps'))}"
        )

    def _render_gap_links(self, gaps):
        box = self.el["detail_gaps"]
        box.clear()
        if isinstance(gaps, str):
            gaps = [gaps]
        with box:
            if not gaps:
                ui.label("Явных пробелов не выявлено 👍").classes("vob-muted")
                return
            for gap_skill in gaps:
                topic = self.handbook.find_topic(gap_skill)
                if topic:
                    section, question, answer, source = topic
                    ui.button(
                        f"{gap_skill} → в учебник", icon="menu_book",
                        on_click=lambda _, s=section, q=question, a=answer, sr=source:
                            self._open_handbook_for(s, q, a, sr),
                    ).props("flat dense no-caps")
                else:
                    ui.button(
                        f"{gap_skill} — нет в учебнике, сгенерировать", icon="auto_awesome",
                        on_click=lambda _, g=gap_skill: self._generate_handbook_topic(g),
                    ).props("flat dense no-caps")

    async def handle_feedback(self):
        if not self.selected_vacancy_id:
            self._show_error("Вакансия не выбрана.")
            return
        feedback = (self.el["input_feedback"].value or "").strip()
        if not feedback:
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        current_letter = self.el["text_letter"].value
        vid = self.selected_vacancy_id
        self.el["btn_feedback"].disable()
        try:
            response = await run.io_bound(
                self.analyzer.adjust_letter,
                current_letter, feedback, v["title"], v["description"],
            )
            new_letter = response.get("letter", current_letter).strip()
            self.repo.save_cover_letter(vid, new_letter, self.el["text_recs"].value)
            self.el["text_letter"].set_value(new_letter)
            self.el["input_feedback"].set_value("")
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_feedback"].enable()

    async def handle_score_letter(self) -> None:
        """ИИ-оценка текущего письма по 4 критериям."""
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию в таблице.")
            return
        letter = self.el["text_letter"].value or ""
        if not letter.strip():
            self._show_error("Письмо пустое — нечего оценивать.")
            return

        btn = self.el["btn_score_letter"]
        btn.disable()
        ui.notify("Оцениваю письмо…", type="info", timeout=2000)

        try:
            v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
            title = (v or {}).get("title", "")
            company = (v or {}).get("company", "")
            description = (v or {}).get("description", "")

            result = await run.io_bound(
                LetterAnalyzer().score_cover_letter,
                letter, title, company, description,
            )
        except Exception as ex:
            self._show_error(f"Ошибка оценки: {ex}")
            btn.enable()
            return

        btn.enable()

        score = result.get("score", 0)
        criteria = result.get("criteria", [])
        summary = result.get("summary", "")

        # Цвет общего балла
        if score >= 80:
            score_color = "#34d399"
        elif score >= 60:
            score_color = "#fbbf24"
        else:
            score_color = "#f87171"

        _CRITERION_COLORS = {
            range(0, 5):  "#f87171",
            range(5, 7):  "#fbbf24",
            range(7, 9):  "#60a5fa",
            range(9, 11): "#34d399",
        }

        def _criterion_color(s: int) -> str:
            for r, c in _CRITERION_COLORS.items():
                if s in r:
                    return c
            return "#a1a1aa"

        with ui.dialog() as dlg, ui.card().style(
            "background:#18181b;border:1px solid #27272a;min-width:500px;max-width:680px"
        ):
            with ui.row().classes("items-center gap-3 w-full"):
                ui.icon("grade", color="primary")
                ui.label("Оценка письма").classes("text-base font-semibold flex-grow").style(
                    "color:#fafafa"
                )
                ui.label(f"{score}/100").style(
                    f"font-size:28px;font-weight:800;color:{score_color}"
                )

            if summary:
                ui.label(summary).classes("text-sm").style("color:#a1a1aa")

            if criteria:
                ui.separator().style("opacity:.3")
                with ui.column().classes("gap-2 w-full"):
                    for crit in criteria:
                        cname  = crit.get("name", "")
                        cscore = int(crit.get("score", 0))
                        cmax   = int(crit.get("max", 10))
                        ccomment = crit.get("comment", "")
                        ccolor = _criterion_color(cscore)
                        with ui.row().classes("w-full items-start gap-2"):
                            with ui.column().classes("flex-grow gap-1"):
                                with ui.row().classes("w-full justify-between items-center"):
                                    ui.label(cname).classes("text-sm font-semibold").style(
                                        "color:#e4e4e7"
                                    )
                                    ui.label(f"{cscore}/{cmax}").classes("text-sm font-bold").style(
                                        f"color:{ccolor}"
                                    )
                                ui.linear_progress(
                                    value=cscore / cmax if cmax else 0,
                                    show_value=False,
                                ).props(f"color={_q(ccolor)} size=4px")
                                if ccomment:
                                    ui.label(ccomment).classes("text-xs").style("color:#71717a")

            with ui.row().classes("justify-end w-full"):
                ui.button("Закрыть", on_click=dlg.close).props("flat no-caps")
        dlg.open()

    def handle_letter_history(self) -> None:
        """Показывает диалог с историей версий письма (до 5) с возможностью восстановить."""
        if not self.selected_vacancy_id:
            ui.notify("Выберите вакансию.", type="warning")
            return
        history = self.repo.get_letter_history(self.selected_vacancy_id)
        if not history:
            ui.notify("История версий пуста — письмо ещё не генерировалось.", type="info")
            return

        with ui.dialog() as dlg, ui.card().style(
            "background:#18181b;border:1px solid #27272a;min-width:580px;max-width:760px"
        ):
            with ui.row().classes("items-center gap-2 w-full"):
                ui.icon("history", color="primary")
                ui.label(f"История версий письма ({len(history)})").classes(
                    "text-base font-semibold flex-grow"
                ).style("color:#fafafa")
                ui.button(icon="close", on_click=dlg.close).props("flat round dense")

            with ui.scroll_area().style("max-height:520px;width:100%"):
                for i, ver in enumerate(history):
                    is_first = i == 0
                    num = len(history) - i
                    date_str = ver.get("created_at", "")[:16].replace("T", " ")
                    preview = (ver.get("letter_text") or "").strip()[:160]
                    if len(ver.get("letter_text") or "") > 160:
                        preview += "…"

                    with ui.card().classes("w-full").style(
                        "background:#27272a;border:1px solid "
                        + ("#a78bfa66" if is_first else "#3f3f46")
                        + ";margin-bottom:8px"
                    ).props("flat"):
                        with ui.row().classes("items-center gap-2 w-full"):
                            with ui.column().classes("gap-0 flex-grow"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(f"Версия {num}").classes(
                                        "text-sm font-semibold"
                                    ).style("color:#e4e4e7")
                                    if is_first:
                                        ui.badge("текущая").style(
                                            "background:#a78bfa33;color:#a78bfa;"
                                            "border:1px solid #a78bfa66"
                                        )
                                ui.label(date_str).classes("text-xs").style("color:#71717a")
                            def _restore(v=ver):
                                self.repo.save_cover_letter(
                                    self.selected_vacancy_id,
                                    v["letter_text"] or "",
                                    v["recommendations"] or "",
                                )
                                self.el["text_letter"].set_value(v["letter_text"] or "")
                                self.el["text_recs"].set_value(v["recommendations"] or "")
                                ui.notify("Версия восстановлена.", type="positive", icon="history")
                                dlg.close()
                            if not is_first:
                                ui.button(
                                    "Восстановить", on_click=_restore
                                ).props("flat no-caps dense").style("color:#a78bfa")
                        ui.label(preview).classes("text-xs").style(
                            "color:#a1a1aa;white-space:pre-wrap;margin-top:4px"
                        )
        dlg.open()

    def copy_letter(self):
        text = self.el["text_letter"].value or ""
        if text:
            ui.clipboard.write(text)
            ui.notify("Скопировано в буфер обмена", type="positive")

    def handle_auto_apply(self):
        if not self.selected_vacancy_id:
            self._show_error("Вакансия не выбрана.")
            return
        letter = self.el["text_letter"].value
        if not letter:
            self._show_error("Письмо не может быть пустым.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        name = f"{v.get('company', '')} — {v.get('title', '')}" if v else self.selected_vacancy_id

        with ui.dialog() as dlg, ui.card():
            ui.label("Подтвердите автоотклик").classes("text-lg font-bold")
            ui.label(f"Отправить отклик с письмом на вакансию:\n«{name}»?")
            with ui.row().classes("justify-end w-full"):
                ui.button("Отмена", on_click=dlg.close).props("flat")
                ui.button("Отправить", on_click=lambda: (dlg.close(), self._do_auto_apply()))
        dlg.open()

    async def _do_auto_apply_async(self):
        vid = self.selected_vacancy_id
        letter = self.el["text_letter"].value
        btn = self.el["btn_auto_apply"]
        btn.disable()
        try:
            success, msg = await run.io_bound(HHParser().auto_apply, vid, letter)
            if success:
                self.repo.update_status(vid, "applied")
                self.refresh_table_data()
                btn.tooltip("Отклик уже отправлен на эту вакансию")
                self._show_info("Отклик отправлен", msg)
            else:
                self._show_error(msg)
                btn.enable()
        except Exception as ex:
            self._show_error(str(ex))
            btn.enable()

    def _do_auto_apply(self):
        ui.timer(0.01, self._do_auto_apply_async, once=True)

    def open_vacancy_in_browser(self):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию в таблице.")
            return
        try:
            webbrowser.open(f"https://hh.ru/vacancy/{self.selected_vacancy_id}")
        except Exception as ex:
            self._show_error(f"Не удалось открыть браузер: {ex}")

    _STATUS_LABEL = {
        "discovered": ("Новая",              "info"),
        "processed":  ("Письмо готово",      "info"),
        "applied":    ("Отклик отправлен",   "positive"),
        "interview":  ("Собеседование",      "positive"),
        "offer":      ("Оффер! 🎉",          "positive"),
        "rejected":   ("Отказ",              "warning"),
    }

    def handle_status_change(self, e):
        if self._suppress_status_change or not self.selected_vacancy_id:
            return
        new_status = e.value
        self.repo.update_status(self.selected_vacancy_id, new_status)
        logging.info(f"Вакансия {self.selected_vacancy_id}: этап → {new_status}")

        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        vac_name = v.get("title", "") if v else ""
        label, ntype = self._STATUS_LABEL.get(new_status, (new_status, "info"))
        ui.notify(
            f"{vac_name}: статус → «{label}»" if vac_name else f"Статус → «{label}»",
            type=ntype,
            icon="flag",
            timeout=3000,
        )

        self.refresh_table_data()

    def handle_notes_save(self):
        if not self.selected_vacancy_id:
            return
        self.repo.update_notes(self.selected_vacancy_id, self.el["detail_notes"].value or "")

    def handle_hr_details_save(self):
        """Сохраняет HR-поля (имя, контакты, дата собеседования) при потере фокуса."""
        if not self.selected_vacancy_id:
            return
        self.repo.update_details(self.selected_vacancy_id, {
            "hr_name":        self.el["detail_hr_name"].value or "",
            "contacts":       self.el["detail_contacts"].value or "",
            "interview_date": self.el["detail_interview_date"].value or "",
            "notes":          self.el["detail_notes"].value or "",
        })

    def _init_salary_field(self):
        exp = int(self.config.get("salary_expectation") or 0)
        self.el["salary_exp"].set_value(str(exp) if exp else "")

    def handle_salary_expectation_change(self):
        raw = (self.el["salary_exp"].value or "").strip()
        value = int(raw) if raw.isdigit() else 0
        self.config.set("salary_expectation", value)
        self.refresh_table_data()

    def _try_autofill_salary(self):
        if int(self.config.get("salary_expectation") or 0):
            return
        try:
            found = extract_salary_from_resume(self.resume.extract_text())
            if found:
                self.config.set("salary_expectation", found)
                self.el["salary_exp"].set_value(str(found))
                logging.info(f"[Salary] Автоизвлечение из резюме: {found} ₽")
        except Exception:
            pass

    def _refresh_resume_label(self):
        path = self.resume.file_path
        self.el["resume_label"].set_text(
            f"📄 {path.name}" if path.exists() else "Резюме не загружено"
        )
