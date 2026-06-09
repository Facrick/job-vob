"""Вкладка «Письма»: генерация, анализ, автоотклик, статус, заметки, резюме."""
import logging
import webbrowser

from nicegui import run, ui

from core.parser import HHParser
from core.utils import extract_salary_from_resume


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
