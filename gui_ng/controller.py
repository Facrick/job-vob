"""controller.py — бизнес-логика интерфейса для NiceGUI-версии.

Переиспользует весь core/* (БД, AI, парсер, матчинг, учебник) без изменений.
Отличия от Flet-контроллера:
  • нет page.update() — NiceGUI реактивен, правка свойств элемента сразу уходит в UI;
  • фоновые задачи — async + run.io_bound; потоковые обновления (поиск) пушатся
    в event loop через loop.call_soon_threadsafe, чтобы апдейты шли в клиентском
    контексте;
  • диалоги/тосты — ui.dialog / ui.notify;
  • выбор файлов — нативный диалог pywebview.
"""

import asyncio
import logging
import re
import shutil
import statistics
import webbrowser
from logging.handlers import RotatingFileHandler

import webview
from nicegui import app, run, ui

from core.ai_engine import LetterAnalyzer, ResumeEntity
from core.config import AppConfig
from core.database import DataExporter, VacancyRepository
from core.exercises import ExerciseBank
from core.handbook import AI_SECTION, QAHandbook
from core.interview_engine import MockInterviewEngine
from core.matching import compute_match_score
from core.parser import HHParser
from core.paths import user_path
from core.search_service import SearchService
from core.skill_heatmap import extract_top_skills
from core.utils import (
    extract_salary_from_resume,
    html_to_markdown,
    normalize_markdown,
    vacancy_desc_to_html,
)
from gui_ng.theme import GRADE_HEX, STATUS_STYLE, match_color


class NiceGuiLogHandler(logging.Handler):
    """Дописывает логи в ui.log-элемент. push() безопасен из любого контекста."""

    def __init__(self, log_element):
        super().__init__()
        self.log_element = log_element

    def emit(self, record: logging.LogRecord):
        try:
            self.log_element.push(self.format(record))
        except Exception:
            pass


class AppController:
    TAB_SCOUT, TAB_LETTERS, TAB_INTERVIEW = "scout", "letters", "interview"
    TAB_ANALYTICS, TAB_HANDBOOK, TAB_LOGS = "analytics", "handbook", "logs"

    def __init__(self):
        self.config = AppConfig()
        self.repo = VacancyRepository()
        self.exporter = DataExporter(self.repo)
        self.resume = ResumeEntity(str(user_path("resume.pdf")))
        self.handbook = QAHandbook()
        self.exercises = ExerciseBank()
        self._analyzer: LetterAnalyzer | None = None
        self._interview_engine: MockInterviewEngine | None = None

        self.selected_vacancy_id: str | None = None
        self.mock_chat_history: list = []
        # Программная установка значения select/toggle триггерит on_change — гасим эхо.
        self._suppress_status_change = False
        self._suppress_mode_change = False

        # UI-элементы (заполняются билдерами вкладок).
        self.el: dict = {}
        self.tabs = None  # ui.tabs для переключения вкладок

        # Состояние учебника.
        self._current_topic: dict | None = None
        self._hb_mode = "sections"
        self._handbook_sections: dict = {}
        self._adding_new_topic = False  # режим создания новой темы через UI
        self._current_exercise: dict | None = None  # {task, reference, rubric, question}

    # ── ленивые тяжёлые сервисы ──────────────────────────────────
    @property
    def analyzer(self) -> LetterAnalyzer:
        if self._analyzer is None:
            self._analyzer = LetterAnalyzer()
        return self._analyzer

    @property
    def interview_engine(self) -> MockInterviewEngine:
        if self._interview_engine is None:
            self._interview_engine = MockInterviewEngine()
        return self._interview_engine

    # ── инициализация после сборки UI ────────────────────────────
    def on_ready(self):
        self._setup_logging_bridge()
        self._init_salary_field()
        self.refresh_table_data()
        self.load_handbook()
        self._reset_topic_pane()
        self._refresh_resume_label()

    def _setup_logging_bridge(self):
        log_dir = user_path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        for h in root.handlers[:]:
            root.removeHandler(h)
        fh = RotatingFileHandler(
            log_dir / "app.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        root.addHandler(fh)
        if self.el.get("logs"):
            ui_handler = NiceGuiLogHandler(self.el["logs"])
            ui_handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
            )
            root.addHandler(ui_handler)
        logging.info("Система логирования инициализирована.")

    def switch_to_tab(self, name: str):
        if self.tabs is not None:
            self.tabs.set_value(name)

    # ── диалоги / тосты ──────────────────────────────────────────
    def _show_error(self, message: str):
        ui.notify(message, type="negative", multi_line=True, close_button=True)

    def _show_info(self, title: str, message: str):
        ui.notify(f"{title}: {message}", type="positive", multi_line=True, close_button=True)

    # ==================================================================
    #  Форматирование (порт из Flet-контроллера)
    # ==================================================================
    @staticmethod
    def _format_salary(s_min, s_max) -> str:
        def fmt(n):
            return f"{int(n):,}".replace(",", " ")

        if s_min and s_max:
            return f"{fmt(s_min)}–{fmt(s_max)} ₽"
        if s_min:
            return f"от {fmt(s_min)} ₽"
        if s_max:
            return f"до {fmt(s_max)} ₽"
        return "з/п не указана"

    def _salary_color(self, s_min, s_max) -> str:
        expectation = int(self.config.get("salary_expectation") or 0)
        if not expectation or (s_min is None and s_max is None):
            return "#9aa0b4"
        upper = s_max if s_max is not None else s_min
        lower = s_min if s_min is not None else s_max
        if lower >= expectation:
            return "#66bb6a"
        if upper >= expectation:
            return "#ff8f00"
        return "#ef5350"

    def _safe_resume_text(self) -> str:
        try:
            return self.resume.extract_text()
        except Exception:
            return ""

    def _recompute_all_match_scores(self):
        resume_text = self._safe_resume_text()
        for v in self.repo.get_vacancies_filtered("all"):
            self.repo.update_match_score(v["id"], compute_match_score(resume_text, v))

    # ==================================================================
    #  Таблица вакансий
    # ==================================================================
    def _row_dict(self, v: dict) -> dict:
        score = v.get("match_score")
        label, scolor = STATUS_STYLE.get(
            v.get("status", ""), (v.get("status", "") or "—", "#9aa0b4")
        )
        return {
            "id": v["id"],
            "match": "—" if score is None else f"{int(score)}%",
            "match_color": match_color(score),
            "company": v.get("company", ""),
            "title": v.get("title", ""),
            "salary": self._format_salary(v.get("salary_min"), v.get("salary_max")),
            "salary_color": self._salary_color(v.get("salary_min"), v.get("salary_max")),
            "status": label,
            "status_color": scolor,
        }

    def refresh_table_data(self):
        if "table" not in self.el:
            return
        status_filter = self.el["status_filter"].value or "all"
        vacancies = self.repo.get_vacancies_filtered(status_filter)
        self.el["table"].rows = [self._row_dict(v) for v in vacancies]
        self.el["table"].update()
        self._update_funnel_counters()
        self._render_funnel()

    def _update_funnel_counters(self):
        all_vac = self.repo.get_vacancies_filtered("all")
        counts: dict[str, int] = {}
        for v in all_vac:
            counts[v.get("status", "")] = counts.get(v.get("status", ""), 0) + 1
        box = self.el.get("funnel_counters")
        if box is None:
            return
        letters = self.repo.count_cover_letters()
        box.clear()
        with box:
            ui.label(f"Всего: {len(all_vac)}").classes("font-bold text-sm")
            for key, (label, color) in STATUS_STYLE.items():
                n = counts.get(key, 0)
                if n:
                    # Насыщенный фон + белый текст: читаемо при любом цвете статуса
                    # (полупрозрачный фон со своим же цветом текста сливался — баг).
                    ui.badge(f"{label}: {n}").style(
                        f"background-color:{color}33;color:#fff;"
                        f"border:1px solid {color}66;font-weight:600"
                    )
            # Письма существуют независимо от текущего этапа воронки — отдельный счётчик.
            ui.badge(f"✉ С письмом: {letters}").style(
                "background-color:#a78bfa33;color:#fff;"
                "border:1px solid #a78bfa66;font-weight:600"
            )

    def on_row_click(self, e):
        # e.args = [event, row, index]
        try:
            row = e.args[1]
        except (IndexError, TypeError):
            return
        self.select_vacancy(row.get("id"))

    def select_vacancy(self, vid: str):
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
        for key in ("btn_generate", "btn_analyze", "btn_open_url"):
            self.el[key].set_visibility(True)

        # Кнопку автоотклика блокируем, если отклик уже отправлен
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

    def toggle_filters(self):
        box = self.el["filters_row"]
        box.set_visibility(not box.visible)

    # ── дашборд воронки (вкладка Аналитика) ──────────────────────
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
        offer = c.get("offer", 0)
        interview = c.get("interview", 0) + offer
        applied = c.get("applied", 0) + interview
        letter = c.get("processed", 0) + applied
        rejected = c.get("rejected", 0)
        metrics = [
            ("Всего", total, "#42a5f5"),
            ("Отклики", applied, "#ff8f00"),
            ("Собеседования", interview, "#ab47bc"),
            ("Офферы", offer, "#66bb6a"),
            ("Отказы", rejected, "#ef5350"),
        ]
        with box:
            with ui.row().classes("gap-3 flex-wrap"):
                for label, value, color in metrics:
                    with ui.card().style(
                        f"background-color:{color}1f;padding:10px 14px"
                    ).props("flat"):
                        ui.label(str(value)).style(
                            f"font-size:22px;font-weight:700;color:{color}"
                        )
                        ui.label(label).classes("text-xs vob-muted")
            ui.separator()
            stages = [
                ("Собрано", total, "#42a5f5"),
                ("Письмо готово", letter, "#5c6bc0"),
                ("Отклик отправлен", applied, "#ff8f00"),
                ("Собеседование", interview, "#ab47bc"),
                ("Оффер", offer, "#66bb6a"),
            ]
            prev = None
            for label, count, color in stages:
                ratio = count / total
                conv = "" if not prev else f"   ·   конверсия {round(count / prev * 100)}%"
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("w-full justify-between"):
                        ui.label(label).classes("font-medium")
                        ui.label(
                            f"{count}  ·  {round(ratio * 100)}% от всех{conv}"
                        ).classes("text-xs vob-muted")
                    ui.linear_progress(value=ratio, show_value=False).props(
                        f"color={_q(color)}"
                    )
                prev = count
            if applied:
                resp = round(interview / applied * 100)
                off = round(offer / interview * 100) if interview else 0
                ui.label(
                    f"Отклик → собеседование: {resp}%      "
                    f"Собеседование → оффер: {off}%"
                ).style("color:#7986cb;font-weight:500;font-size:12px")

    # ==================================================================
    #  Поиск (потоковое обновление таблицы)
    # ==================================================================
    async def handle_search(self):
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
            # Поиск чистит только «Новые» — уже обработанные вакансии остаются в таблице.
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

    # ==================================================================
    #  Генерация / правка письма
    # ==================================================================
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
                # Кнопка остаётся заблокированной — отклик можно отправить только раз
            else:
                self._show_error(msg)
                btn.enable()  # разблокируем только при ошибке
        except Exception as ex:
            self._show_error(str(ex))
            btn.enable()  # разблокируем только при ошибке

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

    # ── этап воронки / заметки / резюме / экспорт ────────────────
    def handle_status_change(self, e):
        if self._suppress_status_change or not self.selected_vacancy_id:
            return
        self.repo.update_status(self.selected_vacancy_id, e.value)
        logging.info(f"Вакансия {self.selected_vacancy_id}: этап → {e.value}")
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

    @staticmethod
    def _native_win():
        """Активное окно pywebview (None в браузерном режиме)."""
        win = getattr(app.native, "main_window", None)
        if win is None and getattr(webview, "windows", None):
            win = webview.windows[0]
        return win

    async def _pick_open_file(self, file_types: tuple[str, ...]) -> str | None:
        """Нативный диалог открытия. create_file_dialog — корутина, ждём на главном loop."""
        win = self._native_win()
        if win is None:
            self._show_error("Нативное окно недоступно.")
            return None
        try:
            result = await win.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types
            )
        except Exception as ex:
            logging.error(f"[FileDialog] open: {ex}")
            self._show_error(f"Не удалось открыть диалог выбора файла: {ex}")
            return None
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    async def _pick_save_file(self, default_name: str) -> str | None:
        """Нативный диалог сохранения. Возвращает путь или None."""
        win = self._native_win()
        if win is None:
            self._show_error("Нативное окно недоступно.")
            return None
        try:
            result = await win.create_file_dialog(
                webview.SAVE_DIALOG, save_filename=default_name
            )
        except Exception as ex:
            logging.error(f"[FileDialog] save: {ex}")
            self._show_error(f"Не удалось открыть диалог сохранения: {ex}")
            return None
        if not result:
            return None
        return result if isinstance(result, str) else result[0]

    async def handle_resume_upload(self):
        path = await self._pick_open_file(("Резюме PDF (*.pdf)",))
        if not path:
            return
        dest = user_path("resume.pdf")
        try:
            shutil.copyfile(path, dest)
            self.resume.file_path = dest
            self.resume._cached_text = None
            self._refresh_resume_label()
            self._recompute_all_match_scores()
            self._try_autofill_salary()
            self.refresh_table_data()
            self._show_info("Резюме обновлено", f"Загружено: {dest.name}. Match пересчитан.")
        except Exception as ex:
            self._show_error(f"Не удалось загрузить резюме: {ex}")

    async def handle_export(self):
        path = await self._pick_save_file("vacancies_export.csv")
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        ok, msg = self.exporter.export_discovered_to_csv(path)
        self._show_info("Экспорт завершён", msg) if ok else self._show_error(msg)

    # ==================================================================
    #  Mock-собеседование
    # ==================================================================
    async def handle_start_mock(self):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        fmt = self.el["combo_format"].value or "tech"
        system_msg = self.interview_engine.get_interview_system_prompt(
            fmt, v["company"], v["title"], v.get("description", "")
        )
        self.mock_chat_history = [{"role": "system", "content": system_msg}]
        self._clear_report()
        self.el["btn_start"].disable()
        try:
            reply = await run.io_bound(
                self.interview_engine.generate_mock_reply, self.mock_chat_history
            )
            self.mock_chat_history.append({"role": "assistant", "content": reply})
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
            self.el["btn_evaluate"].set_visibility(True)
            self._render_mock_chat()
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_start"].enable()

    async def handle_send_chat(self):
        user_text = (self.el["input_chat"].value or "").strip()
        if not user_text or not self.mock_chat_history:
            return
        self.mock_chat_history.append({"role": "user", "content": user_text})
        self.el["input_chat"].set_value("")
        self._render_mock_chat()
        self.el["btn_send"].disable()
        try:
            messages = list(self.mock_chat_history) + [{
                "role": "system",
                "content": "Оцени ответ по 10-балльной шкале, укажи ошибки. Задай следующий вопрос.",
            }]
            reply = await run.io_bound(self.interview_engine.generate_mock_reply, messages)
            self.mock_chat_history.append({"role": "assistant", "content": reply})
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
            self._render_mock_chat()
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_send"].enable()

    async def handle_evaluate_interview(self):
        if len([m for m in self.mock_chat_history if m["role"] == "user"]) < 2:
            self._show_error("Проведите хотя бы 2–3 обмена репликами перед оценкой.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id) if self.selected_vacancy_id else {}
        fmt = self.el["combo_format"].value or "tech"
        self.el["btn_evaluate"].disable()
        try:
            data = await run.io_bound(
                self.interview_engine.evaluate_mock_interview,
                self.mock_chat_history, fmt, v.get("title", ""), v.get("company", ""),
            )
            self._render_report(data)
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["btn_evaluate"].enable()

    def handle_reset_mock(self):
        self.mock_chat_history = []
        if self.selected_vacancy_id:
            self.repo.save_mock_interview(self.selected_vacancy_id, [])
        self.el["chat_arena"].clear()
        self.el["btn_evaluate"].set_visibility(False)
        self._clear_report()

    def _render_mock_chat(self):
        arena = self.el.get("chat_arena")
        if arena is None:
            return
        arena.clear()
        with arena:
            for msg in self.mock_chat_history:
                if msg["role"] == "assistant":
                    ui.chat_message(msg["content"], name="Тимлид", sent=False)
                elif msg["role"] == "user":
                    ui.chat_message(msg["content"], name="Вы", sent=True)

    def _clear_report(self):
        self.el["report_box"].clear()
        with self.el["report_box"]:
            ui.label("Завершите сессию и нажмите «Оценить сессию»").classes(
                "italic vob-muted text-sm"
            )

    def _render_report(self, data: dict):
        box = self.el["report_box"]
        box.clear()
        with box:
            if data.get("summary"):
                ui.label(data["summary"]).classes("text-sm vob-muted")
            for comp in data.get("competencies", []):
                score = int(comp.get("score", 0))
                color = "#66bb6a" if score >= 7 else "#ff8f00" if score >= 4 else "#ef5350"
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("items-center gap-2"):
                        ui.badge(str(score)).style(
                            f"background-color:{color}33;color:#fff;font-weight:700"
                        )
                        ui.label(comp.get("name", "")).classes("font-medium")
                    ui.linear_progress(value=score / 10, show_value=False).props(
                        f"color={_q(color)}"
                    )
                    ui.label(comp.get("comment", "")).classes("text-xs vob-muted")
            strengths = data.get("strengths", [])
            if strengths:
                ui.label("✅ " + "\n✅ ".join(strengths)).classes("text-sm whitespace-pre-line")
            improvements = data.get("improvements", [])
            if improvements:
                ui.label("📌 " + "\n📌 ".join(improvements)).classes("text-sm whitespace-pre-line")
            rec = data.get("recommendation", "")
            if rec:
                color = ("#66bb6a" if "рекомендую" in rec.lower()
                         else "#ff8f00" if "подготовка" in rec.lower() else "#ef5350")
                ui.label(rec).style(
                    f"background-color:{color}20;color:#fff;font-weight:500;"
                    f"border:1px solid {color}55;padding:8px 12px;border-radius:8px"
                )

    # ==================================================================
    #  Аналитика — зарплаты и хитмап
    # ==================================================================
    def draw_analytics_chart(self):
        vacancies = self.repo.get_vacancies_filtered("all")
        mins = [v["salary_min"] for v in vacancies if v.get("salary_min")]
        maxs = [v["salary_max"] for v in vacancies if v.get("salary_max")]
        if not mins and not maxs:
            self._show_info("Нет данных", "В базе нет вакансий с указанными зарплатами.")
            return
        all_s = mins + maxs
        box = self.el["salary_box"]
        box.clear()
        with box:
            with ui.row().classes("gap-3 flex-wrap"):
                stats = [
                    ("Минимум", min(mins) if mins else 0, "#64b5f6"),
                    ("Медиана", int(statistics.median(all_s)), "#7986cb"),
                    ("Среднее", int(sum(all_s) / len(all_s)), "#ba68c8"),
                    ("Максимум", max(maxs) if maxs else 0, "#81c784"),
                ]
                for label, value, color in stats:
                    with ui.card().style(f"background-color:{color}1a;padding:10px 16px").props("flat"):
                        ui.label(label).classes("text-xs vob-muted")
                        ui.label(f"{value:,} ₽".replace(",", " ")).style(
                            f"font-size:16px;font-weight:700;color:{color}"
                        )
                with ui.card().style("background-color:#7986cb14;padding:10px 16px").props("flat"):
                    ui.label("Вакансий с зарплатой").classes("text-xs vob-muted")
                    ui.label(f"{len(mins)} из {len(vacancies)}").classes("text-base font-bold")
            ui.separator()
            buckets = [
                ("< 80 000", 0, 80_000), ("80 000 – 120 000", 80_000, 120_000),
                ("120 000 – 180 000", 120_000, 180_000),
                ("180 000 – 250 000", 180_000, 250_000),
                ("> 250 000", 250_000, 10_000_000),
            ]
            colors = ["#64b5f6", "#7986cb", "#ba68c8", "#9575cd", "#81c784"]
            counts = [(lbl, sum(1 for s in mins if lo <= s < hi)) for lbl, lo, hi in buckets]
            max_count = max((c for _, c in counts), default=0) or 1
            for (lbl, count), color in zip(counts, colors, strict=False):
                pct = max(2, count / max_count * 100)
                with ui.row().classes("items-center gap-2 w-full no-wrap"):
                    ui.label(lbl).classes("text-sm truncate").style("flex:0 0 38%")
                    with ui.element("div").classes("flex-grow").style(
                        "background:#ffffff14;border-radius:4px;height:20px;min-width:0"
                    ):
                        ui.element("div").style(
                            f"height:20px;border-radius:4px;background-color:{color};width:{pct}%"
                        )
                    ui.label(str(count)).classes("text-xs vob-muted").style("flex:0 0 24px")

    def draw_skill_heatmap(self):
        top_n = int(self.el["combo_heatmap_n"].value or 20)
        vacancies = self.repo.get_vacancies_filtered("all")
        if not vacancies:
            self._show_info("Нет данных", "Соберите вакансии на вкладке CRM.")
            return
        skills = extract_top_skills(vacancies, top_n=top_n, min_count=1)
        box = self.el["heatmap_box"]
        box.clear()
        with box:
            if not skills:
                ui.label(
                    "Навыки не найдены. Убедитесь, что у вакансий заполнено поле «Ключевые навыки»."
                ).classes("italic vob-muted")
                return
            # Легенда грейдов (J / M / S).
            with ui.row().classes("gap-2 items-center flex-wrap"):
                ui.label("Грейды:").classes("text-xs vob-muted")
                for tag, grade in (("J — Junior", "Junior"), ("M — Middle", "Middle"),
                                   ("S — Senior/Lead", "Senior/Lead")):
                    ui.badge(tag).style(
                        f"background-color:{GRADE_HEX[grade]};color:#fff;font-weight:500"
                    )
            ui.separator()
            max_count = skills[0]["count"]
            for item in skills:
                ratio = item["count"] / max_count
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label(item["skill"]).classes("text-sm truncate").style(
                            "flex:1 1 0;min-width:0"
                        )
                        for grade in ("Junior", "Middle", "Senior/Lead"):
                            n = item["grades"].get(grade, 0)
                            if not n:
                                continue
                            color = GRADE_HEX[grade]
                            tag = grade[0] if grade != "Senior/Lead" else "S"
                            ui.badge(f"{tag}:{n}").style(
                                f"background-color:{color}33;color:#fff;"
                                f"border:1px solid {color}55;font-weight:600"
                            )
                        ui.badge(str(item["count"])).style(
                            "background-color:#a78bfa33;color:#fff;"
                            "border:1px solid #a78bfa55;font-weight:700"
                        )
                    ui.linear_progress(value=ratio, show_value=False).props("color=primary")

    def handle_clear_logs(self):
        self.el["logs"].clear()

    # ==================================================================
    #  Учебник (порт HandbookController)
    # ==================================================================
    def load_handbook(self):
        try:
            self._handbook_sections = self.handbook.get_all_sections()
        except Exception as e:
            logging.error(f"Не удалось загрузить учебник: {e}")
            self._handbook_sections = {}
        self._render_handbook("")

    def _render_progress(self):
        done, total = self.handbook.progress()
        self.el["hb_progress"].set_value((done / total) if total else 0)
        pct = round(done / total * 100) if total else 0
        self.el["hb_progress_label"].set_text(f"Прогресс {pct}% ({done} из {total})")

    def set_handbook_track(self, track: str):
        self.handbook.set_track(track)
        self._current_topic = None
        self._handbook_sections = self.handbook.get_all_sections()
        self._reset_topic_pane()
        # Сбрасываем поиск, чтобы дерево показывало темы нового трека целиком.
        self.el["hb_search"].set_value("")
        if self._hb_mode == "plan":
            self._render_learning_plan()
        else:
            self._render_handbook("")
        if self._hb_mode == "exercises":
            # Старое задание относилось к прежнему треку — очищаем панель.
            self._reset_exercise_pane()

    def _reset_topic_pane(self):
        self.el["hb_topic_title"].set_text("")
        self.el["hb_topic_badge"].set_text("")
        self.el["hb_empty"].set_visibility(True)
        self.el["hb_answer"].set_visibility(False)
        self.el["hb_topic_divider"].set_visibility(False)
        for k in ("hb_btn_edit", "hb_btn_fav", "hb_btn_studied"):
            self.el[k].set_visibility(False)
        self._exit_edit_mode()

    def on_mode_toggle(self, mode: str):
        if self._suppress_mode_change:
            return
        self.set_handbook_mode(mode)

    def set_handbook_mode(self, mode: str):
        self._hb_mode = mode
        # Синхронизируем сегментированный переключатель без повторного эха.
        self._suppress_mode_change = True
        self.el["hb_mode_toggle"].set_value(mode)
        self._suppress_mode_change = False
        is_plan = mode == "plan"
        is_ex = mode == "exercises"
        # Дерево/поиск нужны в «Разделы»/«Избранное»/«Задания» (для выбора темы).
        self.el["hb_search"].set_visibility(not is_plan)
        self.el["hb_tree"].set_visibility(not is_plan)
        # Справа показываем ровно одну панель из трёх.
        self.el["hb_topic_pane"].set_visibility(not is_plan and not is_ex)
        self.el["hb_plan_box"].set_visibility(is_plan)
        self.el["hb_exercise_box"].set_visibility(is_ex)
        if is_plan:
            self._render_learning_plan()
        else:
            self._render_handbook(self.el["hb_search"].value or "")
        if is_ex:
            self._reset_exercise_pane()

    def handle_handbook_search(self):
        self._render_handbook(self.el["hb_search"].value or "")

    def _render_handbook(self, query: str = ""):
        self._render_progress()
        tree = self.el["hb_tree"]
        tree.clear()
        q = (query or "").strip().lower()
        only_fav = self._hb_mode == "favorites"
        any_shown = False
        with tree:
            for section_name, questions in self._handbook_sections.items():
                sec_match = q in section_name.lower()
                shown = [
                    it for it in questions
                    if (not q or sec_match or q in it.get("question", "").lower())
                    and (not only_fav or self.handbook.is_favorite(it["question"]))
                ]
                if not shown:
                    continue
                any_shown = True
                done, total = self.handbook.section_progress(section_name)
                with ui.expansion(
                    f"{section_name}  ({done}/{total})", value=bool(q) or only_fav
                ).classes("w-full").props("dense"):
                    for it in shown:
                        self._hb_tile(section_name, it)
            if not any_shown:
                if only_fav:
                    msg = "В избранном пока пусто — отметьте темы ★."
                elif not q and not self._handbook_sections:
                    msg = ("В этом направлении пока нет тем. Введите тему в поиск "
                           "и сгенерируйте раздел ИИ, либо смените направление.")
                else:
                    msg = "Ничего не найдено"
                ui.label(msg).classes("italic vob-muted")
            if q and not only_fav:
                term = query.strip()
                ui.button(
                    f"Сгенерировать раздел «{term}» с помощью ИИ", icon="auto_awesome",
                    on_click=lambda _, t=term: self._generate_handbook_topic(t),
                ).props("flat dense no-caps")

    def _hb_tile(self, section_name: str, item: dict):
        q = item["question"]
        src = item.get("source", "")
        check = "✓ " if self.handbook.is_studied(q) else ""
        star = "★ " if self.handbook.is_favorite(q) else ""
        badge = "🤖 " if src == "ai" else ("✏️ " if src == "user" else "")
        data = {"section": section_name, "question": q, "answer": item["answer"], "source": src}
        lbl = ui.label(check + star + badge + q).classes(
            "cursor-pointer text-sm py-1 px-2 rounded hover:bg-white/5 w-full"
        )
        if check:
            lbl.style("color:#81c784")
        lbl.on("click", lambda _, d=data: self._on_tile_click(d))

    def _on_tile_click(self, data: dict):
        """Клик по теме: в режиме «Задания» открываем упражнение, иначе материал."""
        if self._hb_mode == "exercises":
            self.load_exercise(data)
        else:
            self._show_topic(**data)

    def _compute_learning_plan(self) -> list[tuple[str, int]]:
        resume_raw = self._safe_resume_text().lower()
        resume_words = set(re.findall(r"[a-zа-яё0-9+#./]{2,}", resume_raw))
        counts: dict[str, int] = {}
        for v in self.repo.get_vacancies_filtered("all"):
            for raw in (v.get("skills") or "").split(","):
                skill = raw.strip()
                low = skill.lower()
                if not skill or low in ("не указаны", "не указано", "—", "-"):
                    continue
                skill_words = set(re.findall(r"[a-zа-яё0-9+#./]{2,}", low))
                if skill_words and skill_words.issubset(resume_words):
                    continue
                counts[skill] = counts.get(skill, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])[:30]

    def _render_learning_plan(self):
        box = self.el.get("hb_plan_list")
        if box is None:
            return
        box.clear()
        plan = self._compute_learning_plan()
        with box:
            if not plan:
                has_vac = bool(self.repo.get_vacancies_filtered("all"))
                hint = ("Соберите вакансии через CRM — план составится из навыков, "
                        "которые работодатели требуют чаще всего." if not has_vac
                        else "Все навыки из ваших вакансий уже есть в резюме — план пуст.")
                ui.label(hint).classes("italic vob-muted text-sm")
                return
            ui.label(
                "Навыки из ваших вакансий, которых нет в резюме (по частоте). "
                "Жмите «в учебник», чтобы открыть материал, или «сгенерировать»."
            ).classes("text-xs vob-muted")
            for skill, count in plan:
                with ui.row().classes("items-center gap-2 w-full no-wrap"):
                    ui.badge(str(count)).style(
                        "background-color:#a78bfa33;color:#fff;"
                        "border:1px solid #a78bfa55;font-weight:700"
                    )
                    ui.label(skill).classes("text-sm truncate").style("flex:1 1 0;min-width:0")
                    topic = self.handbook.find_topic(skill)
                    if topic:
                        section, question, answer, source = topic
                        ui.button(
                            "в учебник", icon="menu_book",
                            on_click=lambda _, s=section, q=question, a=answer, sr=source:
                                self._open_handbook_for(s, q, a, sr),
                        ).props("flat dense no-caps")
                    else:
                        ui.button(
                            "сгенерировать", icon="auto_awesome",
                            on_click=lambda _, t=skill: self._generate_handbook_topic(t),
                        ).props("flat dense no-caps")

    @staticmethod
    def _is_overlay(source: str) -> bool:
        return source in ("ai", "user")

    def _show_topic(self, section: str, question: str, answer: str, source: str = ""):
        self._current_topic = {
            "section": section, "question": question, "answer": answer, "source": source,
        }
        self.el["hb_topic_title"].set_text(question)
        self.el["hb_topic_badge"].set_text({
            "ai": "🤖 сгенерировано ИИ — проверьте", "user": "✏️ изменено",
        }.get(source, ""))
        self.el["hb_empty"].set_visibility(False)
        self.el["hb_topic_divider"].set_visibility(True)
        self.el["hb_answer"].set_visibility(True)
        raw_md = answer if self._is_overlay(source) else html_to_markdown(answer)
        self.el["hb_answer"].set_content(normalize_markdown(raw_md))
        self.el["hb_btn_edit"].set_visibility(True)
        is_fav = self.handbook.is_favorite(question)
        self.el["hb_btn_fav"].set_visibility(True)
        self.el["hb_btn_fav"].props(f'icon={"star" if is_fav else "star_border"}')
        is_studied = self.handbook.is_studied(question)
        self.el["hb_btn_studied"].set_visibility(True)
        self.el["hb_btn_studied"].props(
            f'icon={"check_circle" if is_studied else "check_circle_outline"}'
        )
        self._exit_edit_mode()

    def handle_handbook_favorite(self):
        if not self._current_topic:
            return
        is_fav = self.handbook.toggle_favorite(self._current_topic["question"])
        self.el["hb_btn_fav"].props(f'icon={"star" if is_fav else "star_border"}')
        self._render_handbook(self.el["hb_search"].value or "")

    def handle_handbook_studied(self):
        if not self._current_topic:
            return
        studied = self.handbook.toggle_studied(self._current_topic["question"])
        self.el["hb_btn_studied"].props(
            f'icon={"check_circle" if studied else "check_circle_outline"}'
        )
        self._render_handbook(self.el["hb_search"].value or "")

    def _section_options(self) -> dict[str, str]:
        """Существующие разделы + раздел ИИ-материалов как варианты для сохранения."""
        names = list(self._handbook_sections.keys())
        if AI_SECTION not in names:
            names.append(AI_SECTION)
        return {n: n for n in names}

    def _enter_edit_mode(self):
        t = self._current_topic or {}
        ans, src = t.get("answer", ""), t.get("source", "")
        raw_md = ans if self._is_overlay(src) else html_to_markdown(ans)
        self.el["hb_editor"].set_value(normalize_markdown(raw_md))
        # Выбор раздела доступен всегда (можно «переложить» материал в другой раздел).
        sel = self.el["hb_edit_section"]
        sel.set_options(self._section_options(), value=t.get("section", AI_SECTION))
        sel.set_visibility(True)
        # Поле названия — только при создании новой темы.
        self.el["hb_edit_title"].set_visibility(self._adding_new_topic)
        self.el["hb_view_box"].set_visibility(False)
        self.el["hb_edit_box"].set_visibility(True)
        self.el["hb_btn_edit"].set_visibility(False)

    def _exit_edit_mode(self):
        self._adding_new_topic = False
        self.el["hb_view_box"].set_visibility(True)
        self.el["hb_edit_box"].set_visibility(False)
        self.el["hb_edit_title"].set_visibility(False)
        self.el["hb_edit_section"].set_visibility(False)
        self.el["hb_btn_edit"].set_visibility(bool(self._current_topic))

    def handle_handbook_edit(self):
        if self._current_topic:
            self._adding_new_topic = False
            self._enter_edit_mode()

    def handle_handbook_add_new(self):
        """Создание новой темы вручную через UI (пункт «Добавить тему»)."""
        self._adding_new_topic = True
        self._current_topic = None
        self.el["hb_topic_title"].set_text("Новая тема")
        self.el["hb_topic_badge"].set_text("✏️ создаётся")
        self.el["hb_empty"].set_visibility(False)
        self.el["hb_answer"].set_visibility(False)
        self.el["hb_topic_divider"].set_visibility(True)
        for k in ("hb_btn_fav", "hb_btn_studied"):
            self.el[k].set_visibility(False)
        self.el["hb_editor"].set_value("")
        self.el["hb_edit_title"].set_value("")
        sel = self.el["hb_edit_section"]
        sel.set_options(self._section_options(), value=AI_SECTION)
        sel.set_visibility(True)
        self.el["hb_edit_title"].set_visibility(True)
        self.el["hb_view_box"].set_visibility(False)
        self.el["hb_edit_box"].set_visibility(True)
        self.el["hb_btn_edit"].set_visibility(False)

    def handle_handbook_cancel(self):
        self._exit_edit_mode()

    def handle_handbook_save(self):
        new_md = (self.el["hb_editor"].value or "").strip()
        section = (self.el["hb_edit_section"].value or "").strip() or AI_SECTION
        if self._adding_new_topic:
            question = (self.el["hb_edit_title"].value or "").strip()
            if not question:
                self._show_error("Укажите название темы.")
                return
        else:
            if not self._current_topic:
                return
            question = self._current_topic["question"]
        if not new_md:
            self._show_error("Текст материала не может быть пустым.")
            return
        self.handbook.add_or_update_topic(section, question, new_md, ai=False)
        self._handbook_sections = self.handbook.get_all_sections()
        self._adding_new_topic = False
        self._show_topic(section, question, new_md, "user")
        self._render_handbook(self.el["hb_search"].value or "")
        self._show_info("Сохранено", f"Материал «{question}» сохранён в раздел «{section}».")

    async def handle_handbook_ai_fix(self):
        if not self._current_topic:
            return
        current = self.el["hb_editor"].value or ""
        instructions = self.el["hb_instr"].value or ""
        title = self._current_topic.get("question", "")
        self.el["hb_btn_ai_fix"].disable()
        try:
            revised = await run.io_bound(
                self.analyzer.revise_handbook_article, title, current, instructions
            )
            if revised:
                self.el["hb_editor"].set_value(revised)
                self.el["hb_instr"].set_value("")
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["hb_btn_ai_fix"].enable()

    def _generate_handbook_topic(self, topic: str, context: str = ""):
        ui.timer(0.01, lambda: self._generate_handbook_topic_async(topic, context), once=True)

    async def _generate_handbook_topic_async(self, topic: str, context: str = ""):
        self.el["hb_empty"].set_visibility(False)
        self.el["hb_answer"].set_visibility(True)
        self.el["hb_answer"].set_content(f"⏳ ИИ пишет раздел «{topic}»...")
        self._exit_edit_mode()
        self.switch_to_tab(self.TAB_HANDBOOK)
        try:
            art = await run.io_bound(
                self.analyzer.generate_handbook_article, topic, context, self.handbook.persona
            )
            if not art.get("answer"):
                self._show_error("ИИ не смог сгенерировать материал. Попробуйте ещё раз.")
                return
            self.handbook.add_or_update_topic(AI_SECTION, art["question"], art["answer"], ai=True)
            self._handbook_sections = self.handbook.get_all_sections()
            self.set_handbook_mode("sections")
            self._render_handbook("")
            self._show_topic(AI_SECTION, art["question"], art["answer"], "ai")
            self._show_info(
                "Материал добавлен",
                f"«{art['question']}» сохранён в раздел «{AI_SECTION}». "
                "Отредактируйте при необходимости и нажмите «Сохранить».",
            )
            self._enter_edit_mode()
        except Exception as ex:
            self._show_error(str(ex))

    def _open_handbook_for(self, section: str, question: str, answer: str, source: str):
        self.switch_to_tab(self.TAB_HANDBOOK)
        # Всегда переходим в режим «Разделы», чтобы правая панель темы была видна
        # (из режима «План» панель темы скрыта).
        self.set_handbook_mode("sections")
        self.el["hb_search"].set_value(question)
        self._render_handbook(question)
        self._show_topic(section, question, answer, source)

    # ── упражнения ───────────────────────────────────────────────
    def _reset_exercise_pane(self):
        self._current_exercise = None
        self.el["ex_topic_label"].set_text("Упражнения")
        self.el["ex_empty"].set_visibility(True)
        self.el["ex_content"].set_visibility(False)
        self.el["ex_result"].set_visibility(False)
        self.el["ex_btn_new"].set_visibility(False)
        self.el["ex_spinner"].set_visibility(False)
        self._show_overall_progress()

    def _show_overall_progress(self):
        """Сводный бейдж: сколько тем зачтено / опробовано."""
        passed, attempted = self.exercises.stats()
        badge = self.el["ex_progress"]
        if attempted:
            badge.set_text(f"✓ Зачтено: {passed} из {attempted}")
            badge.style(
                "background-color:#a78bfa25;color:#fff;"
                "border:1px solid #a78bfa44"
            )
            badge.set_visibility(True)
        else:
            badge.set_visibility(False)

    def _show_topic_progress(self, question: str):
        """Бейдж по конкретной теме: лучший результат и число попыток."""
        prog = self.exercises.get_progress(question)
        badge = self.el["ex_progress"]
        if not prog:
            self._show_overall_progress()
            return
        best = prog.get("best_score", 0)
        attempts = prog.get("attempts", 0)
        color = "#66bb6a" if prog.get("passed") else "#ff8f00"
        mark = "✓ " if prog.get("passed") else ""
        badge.set_text(f"{mark}Лучший: {best}/100 · попыток: {attempts}")
        badge.style(
            f"background-color:{color}33;color:#fff;"
            f"border:1px solid {color}55;font-weight:600"
        )
        badge.set_visibility(True)

    def load_exercise(self, topic: dict):
        """Открывает задание по теме: берёт из банка или генерирует новое."""
        question = topic.get("question", "")
        answer = topic.get("answer", "")
        self.el["ex_topic_label"].set_text(question or "Упражнение")
        self.el["ex_empty"].set_visibility(False)
        self.el["ex_btn_new"].set_visibility(True)
        self.el["ex_result"].set_visibility(False)
        self._show_topic_progress(question)
        bank = self.exercises.get_for_topic(question)
        if bank:
            self._current_exercise = {**bank[-1], "question": question, "answer": answer}
            self._show_exercise()
        else:
            self._generate_exercise(question, answer, save=True)

    def _show_exercise(self):
        ex = self._current_exercise or {}
        self.el["ex_task"].set_content(normalize_markdown(ex.get("task", "")))
        self.el["ex_answer"].set_value("")
        self.el["ex_answer"].props(remove="readonly")
        self.el["ex_result"].set_visibility(False)
        self.el["ex_content"].set_visibility(True)
        self.el["ex_btn_check"].set_visibility(True)

    def handle_exercise_new(self):
        if not self._current_exercise:
            return
        ex = self._current_exercise
        self._generate_exercise(ex.get("question", ""), ex.get("answer", ""), save=True)

    def _generate_exercise(self, question: str, answer: str, save: bool):
        ui.timer(
            0.01,
            lambda: self._generate_exercise_async(question, answer, save),
            once=True,
        )

    async def _generate_exercise_async(self, question: str, answer: str, save: bool):
        self.el["ex_empty"].set_visibility(False)
        self.el["ex_content"].set_visibility(False)
        self.el["ex_spinner"].set_visibility(True)
        try:
            ex = await run.io_bound(
                self.analyzer.generate_validated_exercise,
                question, answer, self.handbook.persona,
            )
        except Exception as ex_err:  # noqa: BLE001
            self._show_error(str(ex_err))
            ex = {}
        finally:
            self.el["ex_spinner"].set_visibility(False)
        if not ex or not ex.get("task"):
            self.el["ex_empty"].set_visibility(True)
            self._show_error("ИИ не смог составить задание. Попробуйте ещё раз.")
            return
        if save:
            self.exercises.add(question, ex)
        self._current_exercise = {**ex, "question": question, "answer": answer}
        self._show_exercise()

    async def handle_exercise_check(self):
        if not self._current_exercise:
            return
        user_answer = (self.el["ex_answer"].value or "").strip()
        if not user_answer:
            self._show_error("Введите решение перед проверкой.")
            return
        ex = self._current_exercise
        self.el["ex_btn_check"].disable()
        self.el["ex_spinner"].set_visibility(True)
        try:
            result = await run.io_bound(
                self.analyzer.grade_exercise,
                ex.get("task", ""), ex.get("reference", ""),
                ex.get("rubric", ""), user_answer,
            )
        except Exception as err:  # noqa: BLE001
            self._show_error(str(err))
            result = None
        finally:
            self.el["ex_spinner"].set_visibility(False)
            self.el["ex_btn_check"].enable()
        if result:
            self._render_exercise_result(result)

    def _render_exercise_result(self, data: dict):
        score = int(data.get("score", 0))
        verdict = data.get("verdict") or (
            "Зачтено" if score >= 70 else "Частично" if score >= 40 else "Не зачтено"
        )
        color = "#66bb6a" if score >= 70 else "#ff8f00" if score >= 40 else "#ef5350"
        badge = self.el["ex_score_badge"]
        badge.set_text(f"{verdict} · {score}/100")
        badge.style(
            f"background-color:{color}33;color:#fff;"
            f"border:1px solid {color}55;font-weight:700"
        )
        parts = []
        correct = data.get("correct") or []
        missing = data.get("missing") or []
        advice = data.get("advice") or ""
        if correct:
            parts.append("**✅ Верно:**\n" + "\n".join(f"- {x}" for x in correct))
        if missing:
            parts.append("**⚠️ Упущено / неверно:**\n" + "\n".join(f"- {x}" for x in missing))
        if advice:
            parts.append(f"**💡 Рекомендация:** {advice}")
        self.el["ex_feedback"].set_content("\n\n".join(parts) or "_Нет деталей._")
        self.el["ex_result"].set_visibility(True)
        # Фиксируем прогресс по теме и обновляем бейдж.
        question = (self._current_exercise or {}).get("question", "")
        if question:
            self.exercises.record_result(question, score, verdict)
            self._show_topic_progress(question)
        # После проверки эталон/критерии остаются скрытыми — показываем только разбор.


# ── вспомогательные функции ──────────────────────────────────────
_HH_UNSAFE = re.compile(
    r"<(script|iframe|object|embed|form|input|button|link|style)[^>]*>.*?</\1>|"
    r"<(script|iframe|object|embed|form|input|button|link|style)[^>]*/?>",
    re.IGNORECASE | re.DOTALL,
)
_HH_ATTR_UNSAFE = re.compile(
    r'\s+on\w+\s*=\s*["\'][^"\']*["\']', re.IGNORECASE
)


def _sanitize_hh_html(html: str) -> str:
    """Оставляет форматирование hh.ru (абзацы, списки, жирный) — убирает только
    скрипты, iframe, обработчики событий. Результат рендерится через ui.html()."""
    if not html:
        return ""
    s = _HH_UNSAFE.sub("", html)
    s = _HH_ATTR_UNSAFE.sub("", s)
    return s.strip()


def _q(hex_color: str) -> str:
    """Quasar принимает цвет как имя или как 'hex' через проп color — отдаём hex без #."""
    return hex_color  # linear_progress принимает CSS-цвет в props color


