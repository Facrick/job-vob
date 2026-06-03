import logging
import random
import shutil
import threading
import webbrowser
from logging.handlers import RotatingFileHandler

import flet as ft
from matplotlib.figure import Figure

from core.ai_engine import LetterAnalyzer, ResumeEntity
from core.config import AppConfig
from core.database import DataExporter, VacancyRepository
from core.handbook import QAHandbook
from core.interview_engine import MockInterviewEngine
from core.matching import compute_match_score
from core.parser import HHParser
from core.paths import user_path
from core.search_service import SearchService
from core.skill_heatmap import GRADE_COLORS, extract_top_skills
from core.utils import extract_salary_from_resume, html_to_markdown
from gui.handbook_controller import HandbookController


class FletLogHandler(logging.Handler):
    """Перенаправляет логи в текстовое поле Flet (thread-safe page.update в 0.85)."""

    def __init__(self, logs_text: ft.Text, page: ft.Page):
        super().__init__()
        self.logs_text = logs_text
        self.page = page

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        try:
            self.logs_text.value = (self.logs_text.value or "") + msg + "\n"
            self.page.update()
        except Exception:
            pass


class MainController:
    TAB_SCOUT, TAB_LETTERS, TAB_INTERVIEW, TAB_ANALYTICS, TAB_HANDBOOK, TAB_LOGS = range(6)

    _STATUS_STYLE = {
        "discovered": ("Новая",     ft.Colors.BLUE_400),
        "processed":  ("Письмо",    ft.Colors.INDIGO_400),
        "applied":    ("Отклик",    ft.Colors.AMBER_700),
        "interview":  ("Интервью",  ft.Colors.PURPLE_400),
        "offer":      ("Оффер",     ft.Colors.GREEN_500),
        "rejected":   ("Отказ",     ft.Colors.RED_400),
    }

    def __init__(self):
        self.config   = AppConfig()
        self.repo     = VacancyRepository()
        self.exporter = DataExporter(self.repo)
        self.resume   = ResumeEntity(str(user_path("resume.pdf")))
        self.handbook = QAHandbook()
        self._analyzer: LetterAnalyzer | None = None
        self._interview_engine: MockInterviewEngine | None = None

        self.view = None
        self.page: ft.Page | None = None
        self.selected_vacancy_id: str | None = None
        self.mock_chat_history: list = []
        self._file_picker: ft.FilePicker | None = None

        self.handbook_ctl = HandbookController(self)

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

    # ------------------------------------------------------------------
    #  Инициализация
    # ------------------------------------------------------------------
    def bind_flet_view(self, view, page: ft.Page):
        self.view = view
        self.page = page
        self._file_picker = ft.FilePicker()
        page.services.append(self._file_picker)
        self._setup_logging_bridge()
        self._init_salary_field()
        self.refresh_table_data()
        self.handbook_ctl.load_handbook()
        self._refresh_resume_label()

    def _setup_logging_bridge(self):
        log_dir = user_path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.INFO)
        for h in root.handlers[:]:
            root.removeHandler(h)
        fh = RotatingFileHandler(log_dir / "app.log", maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S"))
        root.addHandler(fh)
        ui = FletLogHandler(self.view.logs_tab.logs_text, self.page)
        ui.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
        root.addHandler(ui)
        logging.info("Система логирования инициализирована.")

    # ==================================================================
    #  Таблица вакансий
    # ==================================================================
    def refresh_table_data(self):
        if not self.view or not self.page:
            return
        status_filter = self.view.scout_tab.combo_status_filter.value or "all"
        vacancies = self.repo.get_vacancies_filtered(status_filter)
        table = self.view.scout_tab.data_table
        table.rows.clear()
        for v in vacancies:
            table.rows.append(self._make_vacancy_row(v))
        has_rows = bool(vacancies)
        self.view.scout_tab.table_empty_label.visible = not has_rows
        self._update_funnel_counters()
        self._render_funnel()
        self.page.update()

    def _update_funnel_counters(self):
        all_vac = self.repo.get_vacancies_filtered("all")
        counts: dict[str, int] = {}
        for v in all_vac:
            counts[v.get("status", "")] = counts.get(v.get("status", ""), 0) + 1
        row = self.view.scout_tab.funnel_counters
        row.controls.clear()
        row.controls.append(ft.Text(f"Всего: {len(all_vac)}", weight=ft.FontWeight.BOLD, size=12))
        for key, (label, color) in self._STATUS_STYLE.items():
            n = counts.get(key, 0)
            if n:
                row.controls.append(ft.Container(
                    content=ft.Text(f"{label}: {n}", size=12, color=color, weight=ft.FontWeight.W_600),
                    bgcolor=ft.Colors.with_opacity(0.15, color),
                    border_radius=20, padding=ft.Padding(10, 4, 10, 4)))

    def _make_vacancy_row(self, v: dict) -> ft.DataRow:
        return ft.DataRow(
            cells=[
                ft.DataCell(self._match_chip(v.get("match_score"))),
                ft.DataCell(ft.Text(v.get("company", ""), weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(v.get("title", ""))),
                ft.DataCell(self._salary_chip(v.get("salary_min"), v.get("salary_max"))),
                ft.DataCell(self._status_chip(v.get("status", ""))),
            ],
            data=v["id"], on_select_change=self._handle_table_click,
        )

    def _status_chip(self, status: str) -> ft.Control:
        label, color = self._STATUS_STYLE.get(status, (status or "—", ft.Colors.GREY))
        return ft.Container(
            content=ft.Text(label, size=12, color=color, weight=ft.FontWeight.W_600),
            bgcolor=ft.Colors.with_opacity(0.15, color),
            border_radius=20, padding=ft.Padding(10, 4, 10, 4))

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

    # ── Match-score ───────────────────────────────────────────────────
    def _safe_resume_text(self) -> str:
        try:
            return self.resume.extract_text()
        except Exception:
            return ""

    @staticmethod
    def _match_color(score: int):
        if score >= 70:
            return ft.Colors.GREEN_500
        if score >= 40:
            return ft.Colors.AMBER_700
        return ft.Colors.RED_400

    def _salary_color(self, s_min, s_max):
        expectation = int(self.config.get("salary_expectation") or 0)
        if not expectation or (s_min is None and s_max is None):
            return ft.Colors.ON_SURFACE_VARIANT
        upper = s_max if s_max is not None else s_min
        lower = s_min if s_min is not None else s_max
        if lower >= expectation:
            return ft.Colors.GREEN_500
        if upper >= expectation:
            return ft.Colors.AMBER_700
        return ft.Colors.RED_400

    def _salary_chip(self, s_min, s_max) -> ft.Control:
        label = self._format_salary(s_min, s_max)
        color = self._salary_color(s_min, s_max)
        bg = (ft.Colors.with_opacity(0.15, color)
              if color != ft.Colors.ON_SURFACE_VARIANT else None)
        return ft.Container(
            content=ft.Text(label, size=11, color=color),
            bgcolor=bg, border_radius=20, padding=ft.Padding(8, 3, 8, 3))

    def _match_chip(self, score) -> ft.Control:
        if score is None:
            return ft.Text("—", color=ft.Colors.ON_SURFACE_VARIANT, size=12)
        color = self._match_color(int(score))
        return ft.Container(
            content=ft.Text(f"{int(score)}%", size=12, color=color, weight=ft.FontWeight.BOLD),
            bgcolor=ft.Colors.with_opacity(0.15, color),
            border_radius=20, padding=ft.Padding(10, 4, 10, 4))

    def _recompute_all_match_scores(self):
        resume_text = self._safe_resume_text()
        for v in self.repo.get_vacancies_filtered("all"):
            self.repo.update_match_score(v["id"], compute_match_score(resume_text, v))

    # ── Дашборд воронки ───────────────────────────────────────────────
    @staticmethod
    def _metric_card(label: str, value: int, color) -> ft.Control:
        return ft.Container(
            bgcolor=ft.Colors.with_opacity(0.12, color), border_radius=12, padding=ft.Padding(14, 10, 14, 10),
            content=ft.Column(spacing=0, tight=True, controls=[
                ft.Text(str(value), size=22, weight=ft.FontWeight.BOLD, color=color),
                ft.Text(label, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ]))

    def _render_funnel(self):
        if not self.view or not self.page:
            return
        vac = self.repo.get_vacancies_filtered("all")
        total = len(vac)
        box = self.view.analytics_tab.funnel_box
        box.controls.clear()
        if total == 0:
            box.controls.append(ft.Text("Нет данных — соберите вакансии на вкладке CRM.",
                                        italic=True, color=ft.Colors.ON_SURFACE_VARIANT))
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
            ("Всего", total, ft.Colors.BLUE_400),
            ("Отклики", applied, ft.Colors.AMBER_700),
            ("Собеседования", interview, ft.Colors.PURPLE_400),
            ("Офферы", offer, ft.Colors.GREEN_500),
            ("Отказы", rejected, ft.Colors.RED_400),
        ]
        box.controls.append(ft.Row(scroll=ft.ScrollMode.AUTO, spacing=10,
                                   controls=[self._metric_card(*m) for m in metrics]))
        box.controls.append(ft.Divider())
        stages = [
            ("Собрано", total, ft.Colors.BLUE_400),
            ("Письмо готово", letter, ft.Colors.INDIGO_400),
            ("Отклик отправлен", applied, ft.Colors.AMBER_700),
            ("Собеседование", interview, ft.Colors.PURPLE_400),
            ("Оффер", offer, ft.Colors.GREEN_500),
        ]
        prev = None
        for label, count, color in stages:
            ratio = count / total
            conv = "" if not prev else f"   ·   конверсия {round(count / prev * 100)}%"
            box.controls.append(ft.Column(spacing=4, controls=[
                ft.Row([ft.Text(label, weight=ft.FontWeight.W_500), ft.Container(expand=True),
                        ft.Text(f"{count}  ·  {round(ratio * 100)}% от всех{conv}",
                                size=12, color=ft.Colors.ON_SURFACE_VARIANT)]),
                ft.ProgressBar(value=ratio, color=color),
            ]))
            prev = count
        if applied:
            resp = round(interview / applied * 100)
            off = round(offer / interview * 100) if interview else 0
            box.controls.append(ft.Text(
                f"Отклик → собеседование: {resp}%      Собеседование → оффер: {off}%",
                size=12, color=ft.Colors.INDIGO_300, weight=ft.FontWeight.W_500))

    def _handle_table_click(self, e):
        self.selected_vacancy_id = e.control.data
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        scout = self.view.scout_tab
        if v:
            scout.detail_title.value = v.get("title", "Без названия")
            salary = self._format_salary(v.get("salary_min"), v.get("salary_max"))
            score = v.get("match_score")
            match_part = f"   ·   Match {int(score)}%" if score is not None else ""
            scout.detail_meta.value = f"{v.get('company', 'Не указана')}   ·   {salary}{match_part}"
            scout.detail_meta.color = self._salary_color(v.get("salary_min"), v.get("salary_max"))
            scout.detail_skills.value = v.get("skills") or "Не указаны"
            scout.detail_description.value = v.get("description") or "Описание отсутствует."
            scout.detail_analysis.value = "_Нажмите «Анализ ИИ», чтобы получить разбор вакансии._"
            scout.detail_gaps.controls.clear()
            scout.detail_status.value = v.get("status", "discovered")
            scout.detail_status.visible = True
            scout.detail_notes.value = v.get("notes") or ""
            for b in (scout.btn_generate, scout.btn_analyze, scout.btn_open_url):
                b.visible = True

        if v:
            label = f"{v.get('company', '')} — {v.get('title', '')}"
            self.view.letters_tab.vacancy_label.value = label
            self.view.letters_tab.vacancy_label.color = ft.Colors.INDIGO_300
            self.view.letters_tab.vacancy_label.italic = False
            self.view.interview_tab.interview_vacancy_label.value = f"Вакансия: {label}"

        existing = self.repo.get_cover_letter(self.selected_vacancy_id)
        if existing:
            self.view.letters_tab.text_letter.value = existing.get("letter_text", "")
            self.view.letters_tab.text_recs.value = existing.get("recommendations", "")
        else:
            self.view.letters_tab.text_letter.value = ""
            self.view.letters_tab.text_recs.value = ""

        saved_chat = self.repo.get_mock_interview(self.selected_vacancy_id)
        if saved_chat:
            self.mock_chat_history = saved_chat
            self._render_mock_chat()
        else:
            self.mock_chat_history = []
            self.view.interview_tab.chat_arena.controls.clear()
        self.page.update()

    def toggle_filters(self, e):
        scout = self.view.scout_tab
        visible = not scout.filters_row.visible
        scout.filters_row.visible = visible
        scout.btn_toggle_filters.icon = ft.Icons.EXPAND_LESS if visible else ft.Icons.EXPAND_MORE
        scout.btn_toggle_filters.tooltip = "Свернуть фильтры" if visible else "Развернуть фильтры"
        self.page.update()

    # ==================================================================
    #  Фоновые задачи
    # ==================================================================
    def _run_bg(self, job, *, busy=None):
        if busy is not None:
            busy.disabled = True
            self.page.update()

        def _worker():
            try:
                job()
            except Exception as ex:
                logging.error(f"[BG] Задача завершилась с ошибкой: {ex}")
                self._show_error(str(ex))
            finally:
                if busy is not None:
                    busy.disabled = False
                if self.page:
                    self.page.update()

        threading.Thread(target=_worker, daemon=True).start()

    # ── Поиск ─────────────────────────────────────────────────────────
    def handle_search(self, e):
        scout = self.view.scout_tab
        keyword  = scout.input_keyword.value.strip() or "QA Engineer"
        period   = scout.combo_period.value   or "7"
        exp      = scout.combo_exp.value      or "between1And3"
        area     = scout.combo_area.value     or "113"
        # Пустая строка = "Все форматы" — не заменяем на "remote"
        schedule = scout.combo_schedule.value if scout.combo_schedule.value is not None else ""

        scout.search_progress.value = None
        scout.search_progress.visible = True
        scout.search_status.visible = True
        scout.search_status.value = "Запускаю поиск и открываю hh.ru..."

        def progress(idx, total, label=""):
            scout.search_progress.value = (idx / total) if total else None
            scout.search_status.value = f"Обработка {idx}/{total}: {label}"
            if self.page:
                self.page.update()

        def job():
            try:
                self.repo.clear_discovered_vacancies()
                logging.info("🧹 Удалены необработанные вакансии (статус «Новая»).")
                # Очищаем таблицу немедленно
                scout.data_table.rows.clear()
                scout.table_empty_label.visible = True
                if self.page:
                    self.page.update()

                resume_text = self._safe_resume_text()
                found_count = [0]

                def on_vacancy(v: dict):
                    v["match_score"] = compute_match_score(resume_text, v)
                    v.setdefault("status", "discovered")
                    self.repo.save_vacancies([v])
                    found_count[0] += 1
                    scout.table_empty_label.visible = False
                    scout.data_table.rows.append(self._make_vacancy_row(v))
                    self._update_funnel_counters()
                    if self.page:
                        self.page.update()

                SearchService().search(
                    text=keyword, period=int(period), area=int(area), experience=exp,
                    schedule=schedule, page_limit=3, progress_callback=progress,
                    on_vacancy=on_vacancy)
                logging.info(f"💾 Добавлено вакансий: {found_count[0]}")
                self._render_funnel()
                if self.page:
                    self.page.update()
            finally:
                scout.search_progress.visible = False
                scout.search_status.visible = False

        self._run_bg(job, busy=scout.btn_search)

    # ── Генерация письма ──────────────────────────────────────────────
    def handle_generation(self, e):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию в таблице.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        if not v:
            self._show_error("Вакансия не найдена в базе.")
            return

        def job():
            resume_text = self.resume.extract_text()
            response = self.analyzer.generate_cover_letter(resume_text, v["title"], v["company"], v["description"])
            letter = response.get("letter", "").strip()
            recs = "\n".join(f"• {r}" for r in response.get("recommendations", []))
            self.repo.save_cover_letter(self.selected_vacancy_id, letter, recs)
            if v["status"] == "discovered":
                self.repo.update_status(self.selected_vacancy_id, "processed")
            self.view.letters_tab.text_letter.value = letter
            self.view.letters_tab.text_recs.value = recs
            self.view.switch_to_tab(self.TAB_LETTERS)
            self.refresh_table_data()

        self._run_bg(job, busy=self.view.scout_tab.btn_generate)

    # ── ИИ-анализ вакансии ────────────────────────────────────────────
    def handle_analyze(self, e):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию в таблице.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        if not v:
            self._show_error("Вакансия не найдена в базе.")
            return
        scout = self.view.scout_tab
        scout.detail_analysis.value = "⏳ ИИ анализирует вакансию..."
        self.page.update()

        def job():
            try:
                resume_text = self.resume.extract_text()
            except Exception:
                resume_text = ""
            data = self.analyzer.analyze_vacancy(resume_text, v["title"], v["company"], v["description"])
            scout.detail_analysis.value = self._format_analysis(data)
            self._render_gap_links(data.get("gaps", []))

        self._run_bg(job, busy=scout.btn_analyze)

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
            f"**Пробелы:**\n{bullets(data.get('gaps'))}")

    def _render_gap_links(self, gaps):
        box = self.view.scout_tab.detail_gaps
        box.controls.clear()
        if isinstance(gaps, str):
            gaps = [gaps]
        if not gaps:
            box.controls.append(ft.Text("Явных пробелов не выявлено 👍", color=ft.Colors.ON_SURFACE_VARIANT))
            return
        for gap_skill in gaps:
            topic = self.handbook.find_topic(gap_skill)
            if topic:
                section, question, answer, source = topic
                box.controls.append(ft.TextButton(
                    content=ft.Text(f"{gap_skill} → в учебник"), icon=ft.Icons.MENU_BOOK,
                    on_click=lambda e, s=section, q=question, a=answer, sr=source:
                        self.handbook_ctl._open_handbook_for(s, q, a, sr)))
            else:
                box.controls.append(ft.TextButton(
                    content=ft.Text(f"{gap_skill} — нет в учебнике, сгенерировать"), icon=ft.Icons.AUTO_AWESOME,
                    on_click=lambda e, g=gap_skill: self.handbook_ctl._generate_handbook_topic(g)))

    # ── Правка письма ─────────────────────────────────────────────────
    def handle_feedback(self, e):
        if not self.selected_vacancy_id:
            self._show_error("Вакансия не выбрана.")
            return
        feedback = self.view.letters_tab.input_feedback.value.strip()
        if not feedback:
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        current_letter = self.view.letters_tab.text_letter.value

        def job():
            response = self.analyzer.adjust_letter(current_letter, feedback, v["title"], v["description"])
            new_letter = response.get("letter", current_letter).strip()
            self.repo.save_cover_letter(self.selected_vacancy_id, new_letter,
                                        self.view.letters_tab.text_recs.value)
            self.view.letters_tab.text_letter.value = new_letter
            self.view.letters_tab.input_feedback.value = ""

        self._run_bg(job, busy=self.view.letters_tab.btn_feedback)

    def copy_letter(self, e):
        text = self.view.letters_tab.text_letter.value
        if text:
            self.page.clipboard = text
            self.page.update()

    # ── Автоотклик ────────────────────────────────────────────────────
    def handle_auto_apply(self, e):
        if not self.selected_vacancy_id:
            self._show_error("Вакансия не выбрана.")
            return
        letter = self.view.letters_tab.text_letter.value
        if not letter:
            self._show_error("Письмо не может быть пустым.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        name = f"{v.get('company', '')} — {v.get('title', '')}" if v else self.selected_vacancy_id

        dlg = ft.AlertDialog(
            title=ft.Text("Подтвердите автоотклик"),
            content=ft.Text(f"Отправить отклик с сопроводительным письмом на вакансию:\n«{name}»?"),
        )

        def _close(_):
            dlg.open = False
            self.page.update()

        def _confirmed(_):
            dlg.open = False
            self.page.update()

            def job():
                parser = HHParser()
                success, msg = parser.auto_apply(self.selected_vacancy_id, letter)
                if success:
                    self.repo.update_status(self.selected_vacancy_id, "applied")
                    self.refresh_table_data()
                    self._show_info("Отклик отправлен", msg)
                else:
                    self._show_error(msg)

            self._run_bg(job, busy=self.view.letters_tab.btn_auto_apply)

        dlg.actions = [
            ft.TextButton("Отправить", on_click=_confirmed),
            ft.TextButton("Отмена",    on_click=_close),
        ]
        self.page.show_dialog(dlg)

    def open_vacancy_in_browser(self, e):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию в таблице.")
            return
        url = f"https://hh.ru/vacancy/{self.selected_vacancy_id}"
        try:
            webbrowser.open(url)
        except Exception as ex:
            self._show_error(f"Не удалось открыть браузер: {ex}")

    # ── Этап воронки / заметки / резюме / экспорт ─────────────────────
    def handle_status_change(self, e):
        if not self.selected_vacancy_id:
            return
        self.repo.update_status(self.selected_vacancy_id, e.control.value)
        logging.info(f"Вакансия {self.selected_vacancy_id}: этап → {e.control.value}")
        self.refresh_table_data()

    def handle_notes_save(self, e):
        if not self.selected_vacancy_id:
            return
        self.repo.update_notes(self.selected_vacancy_id, e.control.value or "")

    def _try_autofill_salary(self):
        if int(self.config.get("salary_expectation") or 0):
            return  # уже задана вручную — не перетираем
        try:
            text = self.resume.extract_text()
            found = extract_salary_from_resume(text)
            if found:
                self.config.set("salary_expectation", found)
                self.view.scout_tab.salary_exp_field.value = str(found)
                logging.info(f"[Salary] Автоизвлечение из резюме: {found} ₽")
        except Exception:
            pass

    def _init_salary_field(self):
        """Восстанавливает ожидаемую з/п из настроек; при отсутствии — пробует извлечь из резюме."""
        exp = int(self.config.get("salary_expectation") or 0)
        if not exp:
            self._try_autofill_salary()
            exp = int(self.config.get("salary_expectation") or 0)
        self.view.scout_tab.salary_exp_field.value = str(exp) if exp else ""

    def handle_salary_expectation_change(self, e):
        raw = (e.control.value or "").strip()
        value = int(raw) if raw.isdigit() else 0
        self.config.set("salary_expectation", value)
        self.refresh_table_data()

    def _refresh_resume_label(self):
        path = self.resume.file_path
        self.view.scout_tab.resume_label.value = f"📄 {path.name}" if path.exists() else "Резюме не загружено"
        if self.page:
            self.page.update()

    def handle_resume_upload(self, e):
        files = self._file_picker.pick_files(dialog_title="Выберите резюме (PDF)",
                                             allowed_extensions=["pdf"],
                                             file_type=ft.FilePickerFileType.CUSTOM)
        if not files:
            return
        dest = user_path("resume.pdf")
        try:
            shutil.copyfile(files[0].path, dest)
            self.resume.file_path = dest
            self.resume._cached_text = None
            self._refresh_resume_label()
            self._recompute_all_match_scores()
            self._try_autofill_salary()
            self.refresh_table_data()
            self._show_info("Резюме обновлено", f"Загружено: {dest.name}. Match-score пересчитан.")
        except Exception as ex:
            self._show_error(f"Не удалось загрузить резюме: {ex}")

    def handle_export(self, e):
        path = self._file_picker.save_file(dialog_title="Сохранить воронку как CSV",
                                           file_name="vacancies_export.csv",
                                           allowed_extensions=["csv"],
                                           file_type=ft.FilePickerFileType.CUSTOM)
        if not path:
            return
        if not path.lower().endswith(".csv"):
            path += ".csv"
        ok, msg = self.exporter.export_discovered_to_csv(path)
        (self._show_info("Экспорт завершён", msg) if ok else self._show_error(msg))

    # ── Mock-собеседование ────────────────────────────────────────────
    def handle_start_mock(self, e):
        if not self.selected_vacancy_id:
            self._show_error("Выберите вакансию.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        fmt = self.view.interview_tab.combo_format.value or "tech"
        system_msg = self.interview_engine.get_interview_system_prompt(
            fmt, v["company"], v["title"], v.get("description", ""))
        self.mock_chat_history = [{"role": "system", "content": system_msg}]
        self._clear_report()

        def _start():
            reply = self.interview_engine.generate_mock_reply(self.mock_chat_history)
            self.mock_chat_history.append({"role": "assistant", "content": reply})
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
            self.view.interview_tab.btn_evaluate.visible = True
            self._render_mock_chat()

        self._run_bg(_start, busy=self.view.interview_tab.btn_start)

    def handle_evaluate_interview(self, e):
        if len([m for m in self.mock_chat_history if m["role"] == "user"]) < 2:
            self._show_error("Проведите хотя бы 2–3 обмена репликами перед оценкой.")
            return
        v = self.repo.get_vacancy_by_id(self.selected_vacancy_id) if self.selected_vacancy_id else {}
        fmt = self.view.interview_tab.combo_format.value or "tech"

        def job():
            data = self.interview_engine.evaluate_mock_interview(
                self.mock_chat_history, fmt,
                v.get("title", ""), v.get("company", ""))
            self._render_report(data)

        self._run_bg(job, busy=self.view.interview_tab.btn_evaluate)

    def _clear_report(self):
        iv = self.view.interview_tab
        iv.report_placeholder.visible = True
        iv.report_summary.value = ""
        iv.report_competencies.controls.clear()
        iv.report_strengths.value = ""
        iv.report_improvements.value = ""
        iv.report_recommendation.visible = False

    def _render_report(self, data: dict):
        iv = self.view.interview_tab
        iv.report_placeholder.visible = False

        iv.report_summary.value = data.get("summary", "")

        iv.report_competencies.controls.clear()
        for comp in data.get("competencies", []):
            score = int(comp.get("score", 0))
            color = (ft.Colors.GREEN_500 if score >= 7
                     else ft.Colors.AMBER_700 if score >= 4
                     else ft.Colors.RED_400)
            iv.report_competencies.controls.append(ft.Column(spacing=2, controls=[
                ft.Row(spacing=8, controls=[
                    ft.Container(
                        content=ft.Text(str(score), size=13, weight=ft.FontWeight.BOLD, color=color),
                        bgcolor=ft.Colors.with_opacity(0.15, color),
                        border_radius=20, padding=ft.Padding(8, 2, 8, 2),
                        width=40, alignment=ft.Alignment(0, 0),
                    ),
                    ft.Text(comp.get("name", ""), size=13, weight=ft.FontWeight.W_500, expand=True),
                ]),
                ft.ProgressBar(value=score / 10, color=color),
                ft.Text(comp.get("comment", ""), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            ]))

        strengths = data.get("strengths", [])
        if strengths:
            iv.report_strengths.value = "✅ " + "\n✅ ".join(strengths)

        improvements = data.get("improvements", [])
        if improvements:
            iv.report_improvements.value = "📌 " + "\n📌 ".join(improvements)

        rec = data.get("recommendation", "")
        if rec:
            color = (ft.Colors.GREEN_500 if "рекомендую" in rec.lower()
                     else ft.Colors.AMBER_700 if "подготовка" in rec.lower()
                     else ft.Colors.RED_400)
            iv.report_recommendation.visible = True
            iv.report_recommendation.bgcolor = ft.Colors.with_opacity(0.15, color)
            iv.report_recommendation.content.value = rec
            iv.report_recommendation.content.color = color

        if self.page:
            self.page.update()

    def handle_send_chat(self, e):
        user_text = self.view.interview_tab.input_chat.value.strip()
        if not user_text or not self.mock_chat_history:
            return
        self.mock_chat_history.append({"role": "user", "content": user_text})
        self.view.interview_tab.input_chat.value = ""
        self._render_mock_chat()

        def _reply():
            messages = list(self.mock_chat_history) + [{
                "role": "system",
                "content": "Оцени ответ по 10-балльной шкале, укажи ошибки. Задай следующий вопрос."}]
            reply = self.interview_engine.generate_mock_reply(messages)
            self.mock_chat_history.append({"role": "assistant", "content": reply})
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
            self._render_mock_chat()

        self._run_bg(_reply, busy=self.view.interview_tab.btn_send)

    def handle_reset_mock(self, e):
        self.mock_chat_history = []
        if self.selected_vacancy_id:
            self.repo.save_mock_interview(self.selected_vacancy_id, [])
        self.view.interview_tab.chat_arena.controls.clear()
        self.view.interview_tab.btn_evaluate.visible = False
        self._clear_report()
        self.page.update()

    def _render_mock_chat(self):
        arena = self.view.interview_tab.chat_arena
        arena.controls.clear()
        for msg in self.mock_chat_history:
            if msg["role"] == "assistant":
                arena.controls.append(self._chat_bubble("Тимлид", msg["content"],
                                                        align=ft.MainAxisAlignment.START,
                                                        bg=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                                                        icon=ft.Icons.SUPPORT_AGENT))
            elif msg["role"] == "user":
                arena.controls.append(self._chat_bubble("Вы", msg["content"],
                                                        align=ft.MainAxisAlignment.END,
                                                        bg=ft.Colors.INDIGO, icon=ft.Icons.PERSON))
        self.page.update()

    @staticmethod
    def _chat_bubble(author, text, *, align, bg, icon):
        bubble = ft.Container(
            bgcolor=bg, border_radius=14, padding=ft.Padding(14, 10, 14, 10),
            content=ft.Column(spacing=4, tight=True, controls=[
                ft.Row(spacing=6, controls=[
                    ft.Icon(icon, size=14, color=ft.Colors.WHITE70),
                    ft.Text(author, size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE70)]),
                ft.Text(text, selectable=True)]))
        return ft.Row(alignment=align, controls=[ft.Container(content=bubble, width=560)])

    # ── Аналитика (график зарплат) ────────────────────────────────────
    def draw_analytics_chart(self, e):
        salaries = [v["salary_min"] for v in self.repo.get_vacancies_filtered("all") if v.get("salary_min")]
        if not salaries:
            self._show_info("Нет данных", "В базе нет вакансий с указанными зарплатами.")
            return
        fig = Figure()
        ax = fig.add_subplot(111)
        ax.hist(salaries, bins=20, color="skyblue", edgecolor="black")
        ax.set_title("Распределение зарплат")
        ax.set_xlabel("Зарплата, ₽")
        ax.set_ylabel("Количество вакансий")
        path = str(user_path("data/chart.png"))
        fig.savefig(path)
        self.view.analytics_tab.chart_image.src = path
        self.view.analytics_tab.chart_image.visible = True
        self.page.update()

    def draw_skill_heatmap(self, e):
        top_n = int(self.view.analytics_tab.combo_heatmap_n.value or 20)
        vacancies = self.repo.get_vacancies_filtered("all")
        if not vacancies:
            self._show_info("Нет данных", "Соберите вакансии на вкладке CRM.")
            return

        skills = extract_top_skills(vacancies, top_n=top_n, min_count=1)
        box = self.view.analytics_tab.heatmap_box
        box.controls.clear()

        if not skills:
            box.controls.append(ft.Text(
                "Навыки не найдены. Убедитесь, что у вакансий заполнено поле «Ключевые навыки».",
                italic=True, color=ft.Colors.ON_SURFACE_VARIANT,
            ))
            self.page.update()
            return

        max_count = skills[0]["count"]
        grade_order = ["Junior", "Middle", "Senior/Lead"]

        for item in skills:
            ratio = item["count"] / max_count
            grade_chips = []
            for grade in grade_order:
                n = item["grades"].get(grade, 0)
                if not n:
                    continue
                color = getattr(ft.Colors, GRADE_COLORS[grade])
                label = f"{'J' if grade == 'Junior' else 'M' if grade == 'Middle' else 'S'}:{n}"
                grade_chips.append(ft.Container(
                    content=ft.Text(label, size=10, color=color, weight=ft.FontWeight.W_500),
                    bgcolor=ft.Colors.with_opacity(0.15, color),
                    border_radius=12, padding=ft.Padding(5, 1, 5, 1),
                ))

            count_chip = ft.Container(
                content=ft.Text(str(item["count"]), size=11,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.INDIGO_300),
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.INDIGO_300),
                border_radius=12, padding=ft.Padding(7, 1, 7, 1),
            )
            box.controls.append(ft.Column(spacing=3, controls=[
                ft.Row(spacing=6, controls=[
                    ft.Container(
                        content=ft.Text(item["skill"], size=12, no_wrap=True,
                                        overflow=ft.TextOverflow.ELLIPSIS),
                        width=160,
                    ),
                    *grade_chips,
                    ft.Container(expand=True),
                    count_chip,
                ]),
                ft.ProgressBar(value=ratio, color=ft.Colors.INDIGO_400, bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST),
            ]))

        if self.page:
            self.page.update()

    # ── Диалоги ───────────────────────────────────────────────────────
    def handle_clear_logs(self, e):
        self.view.logs_tab.logs_text.value = ""
        if self.page:
            self.page.update()

    def _show_error(self, message: str):
        if not self.page:
            return
        self.page.show_dialog(ft.AlertDialog(title=ft.Text("Ошибка", color=ft.Colors.RED),
                                             content=ft.Text(message)))

    def _show_info(self, title: str, message: str):
        if not self.page:
            return
        self.page.show_dialog(ft.AlertDialog(title=ft.Text(title), content=ft.Text(message)))
