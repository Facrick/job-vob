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
from core.handbook import AI_SECTION, QAHandbook
from core.matching import compute_match_score
from core.parser import HHParser
from core.paths import user_path
from core.search_service import SearchService
from core.skill_heatmap import GRADE_COLORS, extract_top_skills
from core.utils import extract_salary_from_resume, html_to_markdown


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

        self.view = None
        self.page: ft.Page | None = None
        self.selected_vacancy_id: str | None = None
        self.mock_chat_history: list = []
        self._file_picker: ft.FilePicker | None = None
        self._current_topic: dict | None = None
        self._hb_mode: str = "sections"
        self._deck: list[dict] = []
        self._cards_done: int = 0
        self._handbook_sections: dict = {}

    @property
    def analyzer(self) -> LetterAnalyzer:
        if self._analyzer is None:
            self._analyzer = LetterAnalyzer()
        return self._analyzer

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
        self._load_handbook()
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
    #  Учебник
    # ==================================================================
    def _load_handbook(self):
        try:
            self._handbook_sections = self.handbook.get_all_sections()
        except Exception as e:
            logging.error(f"Не удалось загрузить учебник: {e}")
            self._handbook_sections = {}
        self._render_handbook("")

    def _tile(self, section_name: str, item: dict) -> ft.Control:
        q = item["question"]
        src = item.get("source", "")
        check = "✓ " if self.handbook.is_studied(q) else ""
        star = "★ " if self.handbook.is_favorite(q) else ""
        badge = "🤖 " if src == "ai" else ("✏️ " if src == "user" else "")
        return ft.ListTile(
            title=ft.Text(check + star + badge + q, size=13,
                          color=ft.Colors.GREEN_300 if check else None),
            data={"section": section_name, "question": q, "answer": item["answer"], "source": src},
            on_click=self._handle_handbook_click, dense=True,
        )

    def _render_progress(self):
        done, total = self.handbook.progress()
        hb = self.view.handbook_tab
        hb.progress_bar.value = (done / total) if total else 0
        pct = round(done / total * 100) if total else 0
        hb.progress_label.value = f"Прогресс {pct}% ({done} из {total})"

    def _render_handbook(self, query: str = ""):
        self._render_progress()
        tree = self.view.handbook_tab.tree_handbook
        tree.controls.clear()

        if self._hb_mode == "plan":
            self._render_learning_plan(tree)
            self.page.update()
            return

        q = (query or "").strip().lower()
        only_fav = self._hb_mode == "favorites"
        for section_name, questions in self._handbook_sections.items():
            sec_match = q in section_name.lower()
            shown = [
                it for it in questions
                if (not q or sec_match or q in it.get("question", "").lower())
                and (not only_fav or self.handbook.is_favorite(it["question"]))
            ]
            if not shown:
                continue
            done, total = self.handbook.section_progress(section_name)
            tree.controls.append(ft.ExpansionTile(
                title=ft.Text(f"{section_name}  ({done}/{total})", weight=ft.FontWeight.BOLD, size=14),
                controls=[self._tile(section_name, it) for it in shown],
                expanded=bool(q) or only_fav,
            ))
        if not tree.controls:
            msg = "В избранном пока пусто — отметьте темы ★." if only_fav else "Ничего не найдено"
            tree.controls.append(ft.Text(msg, italic=True, color=ft.Colors.ON_SURFACE_VARIANT))
        if q and not only_fav:
            term = query.strip()
            tree.controls.append(ft.TextButton(
                content=ft.Text(f"Сгенерировать раздел «{term}» с помощью ИИ"),
                icon=ft.Icons.AUTO_AWESOME,
                on_click=lambda e, t=term: self._generate_handbook_topic(t)))
        self.page.update()

    _ACTIVE_BTN_STYLE = ft.ButtonStyle(
        bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.INDIGO_300),
        color=ft.Colors.INDIGO_300,
    )
    _INACTIVE_BTN_STYLE = ft.ButtonStyle(bgcolor=None, color=None)

    def set_handbook_mode(self, mode: str):
        self._hb_mode = mode
        hb = self.view.handbook_tab
        mode_btns = {
            "sections":  hb.btn_mode_sections,
            "favorites": hb.btn_mode_fav,
            "plan":      hb.btn_mode_plan,
            "cards":     hb.btn_mode_cards,
        }
        for m, btn in mode_btns.items():
            btn.style = self._ACTIVE_BTN_STYLE if m == mode else self._INACTIVE_BTN_STYLE
        is_cards = mode == "cards"
        hb.search_field.visible = not is_cards
        hb.tree_handbook.visible = not is_cards
        hb.cards_controls.visible = is_cards
        hb.topic_pane.visible = not is_cards
        hb.card_box.visible = is_cards
        if is_cards:
            self._deck = []
            hb.card_progress.value = ""
            hb.card_question.value = "Выберите область и нажмите «Начать»."
            hb.btn_reveal.visible = False
            hb.card_answer_box.visible = False
            hb.card_actions.visible = False
            self._render_progress()
            self.page.update()
        else:
            self._render_handbook(hb.search_field.value)

    def handle_handbook_search(self, e):
        self._render_handbook(e.control.value)

    # ── План обучения ─────────────────────────────────────────────────
    def _compute_learning_plan(self) -> list[tuple[str, int]]:
        resume = self._safe_resume_text().lower()
        counts: dict[str, int] = {}
        for v in self.repo.get_vacancies_filtered("all"):
            for raw in (v.get("skills") or "").split(","):
                skill = raw.strip()
                low = skill.lower()
                if not skill or low in ("не указаны", "не указано") or low in resume:
                    continue
                counts[skill] = counts.get(skill, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])[:25]

    def _render_learning_plan(self, tree):
        plan = self._compute_learning_plan()
        if not plan:
            tree.controls.append(ft.Text(
                "План пуст: соберите вакансии (CRM) и загрузите резюме — "
                "сюда попадут требуемые навыки, которых нет в резюме.",
                italic=True, color=ft.Colors.ON_SURFACE_VARIANT))
            return
        tree.controls.append(ft.Text("Навыки из ваших вакансий, которых нет в резюме (по частоте):",
                                     size=12, color=ft.Colors.ON_SURFACE_VARIANT))
        for skill, count in plan:
            topic = self.handbook.find_topic(skill)
            if topic:
                section, question, answer, source = topic
                action = ft.TextButton(
                    content=ft.Text("в учебник"), icon=ft.Icons.MENU_BOOK,
                    on_click=lambda e, s=section, q=question, a=answer, sr=source:
                        self._open_handbook_for(s, q, a, sr))
            else:
                action = ft.TextButton(
                    content=ft.Text("сгенерировать"), icon=ft.Icons.AUTO_AWESOME,
                    on_click=lambda e, t=skill: self._generate_handbook_topic(t))
            tree.controls.append(ft.Row(vertical_alignment=ft.CrossAxisAlignment.CENTER, controls=[
                ft.Container(content=ft.Text(str(count), size=11, weight=ft.FontWeight.BOLD,
                                             color=ft.Colors.INDIGO_300),
                             bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.INDIGO_300),
                             border_radius=20, padding=ft.Padding(8, 2, 8, 2)),
                ft.Text(skill, size=13, expand=True), action,
            ]))

    def handle_handbook_favorite(self, e):
        if not self._current_topic:
            return
        is_fav = self.handbook.toggle_favorite(self._current_topic["question"])
        hb = self.view.handbook_tab
        hb.btn_fav.icon = ft.Icons.STAR if is_fav else ft.Icons.STAR_BORDER
        hb.btn_fav.tooltip = "Убрать из избранного" if is_fav else "В избранное"
        self._render_handbook(hb.search_field.value)

    def handle_handbook_studied(self, e):
        if not self._current_topic:
            return
        studied = self.handbook.toggle_studied(self._current_topic["question"])
        hb = self.view.handbook_tab
        hb.btn_studied.icon = ft.Icons.CHECK_CIRCLE if studied else ft.Icons.CHECK_CIRCLE_OUTLINE
        hb.btn_studied.tooltip = "Снять отметку" if studied else "Отметить изученным"
        self._render_handbook(hb.search_field.value)

    @staticmethod
    def _is_overlay(source: str) -> bool:
        return source in ("ai", "user")

    def _show_topic(self, section: str, question: str, answer: str, source: str = ""):
        hb = self.view.handbook_tab
        self._current_topic = {"section": section, "question": question, "answer": answer, "source": source}
        hb.topic_title.value = question
        hb.topic_badge.value = {"ai": "🤖 сгенерировано ИИ — проверьте", "user": "✏️ изменено"}.get(source, "")
        hb.text_handbook.value = answer if self._is_overlay(source) else html_to_markdown(answer)
        hb.btn_edit.visible = True
        is_fav = self.handbook.is_favorite(question)
        hb.btn_fav.visible = True
        hb.btn_fav.icon = ft.Icons.STAR if is_fav else ft.Icons.STAR_BORDER
        hb.btn_fav.tooltip = "Убрать из избранного" if is_fav else "В избранное"
        is_studied = self.handbook.is_studied(question)
        hb.btn_studied.visible = True
        hb.btn_studied.icon = ft.Icons.CHECK_CIRCLE if is_studied else ft.Icons.CHECK_CIRCLE_OUTLINE
        hb.btn_studied.tooltip = "Снять отметку" if is_studied else "Отметить изученным"
        self._exit_edit_mode()

    def _enter_edit_mode(self):
        hb = self.view.handbook_tab
        t = self._current_topic or {}
        ans, src = t.get("answer", ""), t.get("source", "")
        hb.editor.value = ans if self._is_overlay(src) else html_to_markdown(ans)
        hb.view_box.visible = False
        hb.edit_box.visible = True
        hb.btn_edit.visible = False

    def _exit_edit_mode(self):
        hb = self.view.handbook_tab
        hb.view_box.visible = True
        hb.edit_box.visible = False
        hb.btn_edit.visible = bool(self._current_topic)

    def _handle_handbook_click(self, e):
        d = e.control.data or {}
        self._show_topic(d.get("section", ""), d.get("question", ""), d.get("answer", ""), d.get("source", ""))
        self.page.update()

    def handle_handbook_edit(self, e):
        if self._current_topic:
            self._enter_edit_mode()
            self.page.update()

    def handle_handbook_cancel(self, e):
        self._exit_edit_mode()
        self.page.update()

    def handle_handbook_save(self, e):
        if not self._current_topic:
            return
        t = self._current_topic
        new_md = self.view.handbook_tab.editor.value or ""
        self.handbook.add_or_update_topic(t["section"], t["question"], new_md, ai=False)
        self._handbook_sections = self.handbook.get_all_sections()
        self._show_topic(t["section"], t["question"], new_md, "user")
        self._render_handbook(self.view.handbook_tab.search_field.value)
        self._show_info("Сохранено", "Раздел учебника обновлён.")

    def handle_handbook_ai_fix(self, e):
        if not self._current_topic:
            return
        hb = self.view.handbook_tab
        current = hb.editor.value or ""
        instructions = hb.instr_field.value or ""
        title = self._current_topic.get("question", "")

        def job():
            revised = self.analyzer.revise_handbook_article(title, current, instructions)
            if revised:
                hb.editor.value = revised
                hb.instr_field.value = ""

        self._run_bg(job, busy=hb.btn_ai_fix)

    def handle_handbook_generate(self, e):
        topic = (self.view.handbook_tab.search_field.value or "").strip()
        if topic:
            self._generate_handbook_topic(topic)

    def _generate_handbook_topic(self, topic: str, context: str = ""):
        hb = self.view.handbook_tab
        hb.text_handbook.value = f"⏳ ИИ пишет раздел «{topic}»..."
        self._exit_edit_mode()
        self.page.update()

        def job():
            art = self.analyzer.generate_handbook_article(topic, context)
            if not art.get("answer"):
                self._show_error("ИИ не смог сгенерировать материал. Попробуйте ещё раз.")
                return
            self.handbook.add_or_update_topic(AI_SECTION, art["question"], art["answer"], ai=True)
            self._handbook_sections = self.handbook.get_all_sections()
            self._render_handbook("")
            self._show_topic(AI_SECTION, art["question"], art["answer"], "ai")
            self._enter_edit_mode()
            self.view.switch_to_tab(self.TAB_HANDBOOK)

        self._run_bg(job)

    def _open_handbook_for(self, section: str, question: str, answer: str, source: str):
        hb = self.view.handbook_tab
        if self._hb_mode != "sections":
            self.set_handbook_mode("sections")
        hb.search_field.value = question
        self._render_handbook(question)
        self._show_topic(section, question, answer, source)
        self.view.switch_to_tab(self.TAB_HANDBOOK)

    # ── Флеш-карточки ─────────────────────────────────────────────────
    def handle_cards_start(self, e):
        hb = self.view.handbook_tab
        scope = hb.cards_scope.value
        deck: list[dict] = []
        for section, items in self.handbook.get_all_sections().items():
            for it in items:
                q = it["question"]
                if scope == "favorites" and not self.handbook.is_favorite(q):
                    continue
                if scope == "unstudied" and self.handbook.is_studied(q):
                    continue
                deck.append({"section": section, "question": q,
                             "answer": it["answer"], "source": it.get("source", "")})
        random.shuffle(deck)
        self._deck = deck
        self._cards_done = 0
        if not deck:
            hb.card_progress.value = ""
            hb.card_question.value = "Нет карточек для выбранной области."
            hb.btn_reveal.visible = False
            hb.card_answer_box.visible = False
            hb.card_actions.visible = False
            self.page.update()
            return
        self._show_card()

    def _show_card(self):
        hb = self.view.handbook_tab
        if not self._deck:
            hb.card_progress.value = f"Готово! Отмечено изученными: {self._cards_done}."
            hb.card_question.value = "🎉 Все карточки пройдены."
            hb.btn_reveal.visible = False
            hb.card_answer_box.visible = False
            hb.card_actions.visible = False
            self._render_progress()
            self.page.update()
            return
        hb.card_progress.value = f"Знаю: {self._cards_done}   ·   Осталось: {len(self._deck)}"
        hb.card_question.value = self._deck[0]["question"]
        hb.btn_reveal.visible = True
        hb.card_answer_box.visible = False
        hb.card_actions.visible = False
        self.page.update()

    def handle_cards_reveal(self, e):
        if not self._deck:
            return
        card = self._deck[0]
        hb = self.view.handbook_tab
        hb.card_answer.value = card["answer"] if self._is_overlay(card["source"]) else html_to_markdown(card["answer"])
        hb.btn_reveal.visible = False
        hb.card_answer_box.visible = True
        hb.card_actions.visible = True
        self.page.update()

    def handle_cards_know(self, e):
        if not self._deck:
            return
        card = self._deck.pop(0)
        if not self.handbook.is_studied(card["question"]):
            self.handbook.toggle_studied(card["question"])
        self._cards_done += 1
        self._show_card()

    def handle_cards_repeat(self, e):
        if not self._deck:
            return
        self._deck.append(self._deck.pop(0))
        self._show_card()

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
        for gap in gaps:
            topic = self.handbook.find_topic(gap)
            if topic:
                section, question, answer, source = topic
                box.controls.append(ft.TextButton(
                    content=ft.Text(f"{gap} → в учебник"), icon=ft.Icons.MENU_BOOK,
                    on_click=lambda e, s=section, q=question, a=answer, sr=source:
                        self._open_handbook_for(s, q, a, sr)))
            else:
                box.controls.append(ft.TextButton(
                    content=ft.Text(f"{gap} — нет в учебнике, сгенерировать"), icon=ft.Icons.AUTO_AWESOME,
                    on_click=lambda e, g=gap: self._generate_handbook_topic(g)))

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
        system_msg = self.analyzer.get_interview_system_prompt(
            fmt, v["company"], v["title"], v.get("description", ""))
        self.mock_chat_history = [{"role": "system", "content": system_msg}]
        self._clear_report()

        def _start():
            reply = self.analyzer.generate_mock_reply(self.mock_chat_history)
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
            data = self.analyzer.evaluate_mock_interview(
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
            reply = self.analyzer.generate_mock_reply(messages)
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
