"""Базовый класс AppController: инициализация и общие утилиты."""
import logging
from logging.handlers import RotatingFileHandler

from nicegui import ui

from core.ai_engine import LetterAnalyzer, ResumeEntity
from core.config import AppConfig
from core.database import DataExporter, VacancyRepository
from core.exercises import ExerciseBank
from core.handbook import QAHandbook
from core.interview_engine import MockInterviewEngine
from core.paths import user_path


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


class _AppControllerBase:
    """Базовая часть AppController: инициализация, ленивые сервисы, общие утилиты."""

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
        self._suppress_status_change = False
        self._suppress_mode_change = False

        # UI-элементы (заполняются билдерами вкладок).
        self.el: dict = {}
        self.tabs = None  # ui.tabs для переключения вкладок

        # Состояние учебника.
        self._current_topic: dict | None = None
        self._hb_mode = "sections"
        self._handbook_sections: dict = {}
        self._adding_new_topic = False
        self._current_exercise: dict | None = None

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
        ui.timer(1.0, self._check_hh_auth_async, once=True)

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

    # ── форматирование ────────────────────────────────────────────
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
        from core.matching import compute_match_score
        resume_text = self._safe_resume_text()
        for v in self.repo.get_vacancies_filtered("all"):
            self.repo.update_match_score(v["id"], compute_match_score(resume_text, v))
