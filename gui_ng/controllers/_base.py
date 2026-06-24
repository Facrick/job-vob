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

# Ставится в True после первой настройки file-логгера в этом процессе.
# Защищает от навешивания дублирующих RotatingFileHandler при каждом коннекте.
_FILE_LOG_READY = False


def _find_resume() -> str:
    """Возвращает путь к существующему файлу резюме в user_path, приоритет по расширению."""
    for ext in (".pdf", ".docx", ".doc", ".txt", ".rtf"):
        p = user_path(f"resume{ext}")
        if p.exists():
            return str(p)
    return str(user_path("resume.pdf"))


class NiceGuiLogHandler(logging.Handler):
    """Дописывает логи в ui.log-элемент.

    Защита от бесконечной рекурсии: push() для мёртвого клиента заставляет
    NiceGUI вызвать log.warning(), который снова попадает сюда → push → … .
    Поэтому: (1) игнорируем логи самого nicegui, (2) реентрант-флаг гасит
    повторный вход в emit во время текущего push().
    """

    def __init__(self, log_element, client_id=None):
        super().__init__()
        self.log_element = log_element
        self._emitting = False
        self._client_id = client_id

    def emit(self, record: logging.LogRecord):
        if record.name.startswith("nicegui"):
            return
        if self._emitting:
            return
        self._emitting = True
        try:
            from nicegui.client import Client
            client_id = getattr(self, "_client_id", None)
            if client_id is not None and client_id not in Client.instances:
                return
            self.log_element.push(self.format(record))
        except Exception:
            pass
        finally:
            self._emitting = False


class _AppControllerBase:
    """Базовая часть AppController: инициализация, ленивые сервисы, общие утилиты."""

    TAB_SCOUT, TAB_LETTERS, TAB_INTERVIEW = "scout", "letters", "interview"
    TAB_ANALYTICS, TAB_HANDBOOK, TAB_LOGS = "analytics", "handbook", "logs"

    def __init__(self):
        self.config = AppConfig()
        self.repo = VacancyRepository()
        self.exporter = DataExporter(self.repo)
        self.resume = ResumeEntity(str(_find_resume()))
        self.handbook = QAHandbook()
        self.exercises = ExerciseBank()
        self._analyzer: LetterAnalyzer | None = None
        self._interview_engine: MockInterviewEngine | None = None

        self.selected_vacancy_id: str | None = None
        self.mock_chat_history: list = []

        # Общий кэш статуса авторизации hh.ru: CRM и Аналитика читают его,
        # чтобы не поднимать headless-браузер на каждую проверку/сбор.
        self._hh_auth_cached: bool | None = None
        self._hh_auth_checked_at: float = 0.0
        self._hh_auth_force_recheck = False
        self._suppress_status_change = False
        self._suppress_mode_change = False
        self._search_cancelled = False

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
        from nicegui import context as _ctx
        self._client_id = _ctx.client.id
        self._setup_logging_bridge()
        self._init_salary_field()
        self.refresh_table_data()
        self.load_handbook()
        self._reset_topic_pane()
        self._refresh_resume_label()
        self._refresh_settings_ui()
        ui.timer(1.0, self._check_hh_auth_async, once=True)
        self._restore_autosync_state()
        self._autoload_analytics()

    def _autoload_analytics(self):
        """Сразу строит timeline и хитмап навыков. Зарплаты соискателей — по кнопке."""
        for draw in (self.draw_timeline, self.draw_skill_heatmap):
            try:
                draw()
            except Exception as ex:
                logging.warning(f"Автозагрузка аналитики ({draw.__name__}): {ex}")

    def _setup_logging_bridge(self):
        # on_ready() вызывается на КАЖДОЕ открытие страницы (каждый клиент).
        # File-handler должен ставиться один раз на процесс — иначе на тот же
        # app.log вешается N хендлеров с открытыми дескрипторами, и ротация
        # падает с PermissionError (файл залочен самим же приложением на Windows).
        log_dir = user_path("logs")
        log_dir.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        root.setLevel(logging.DEBUG)

        global _FILE_LOG_READY
        if not _FILE_LOG_READY:
            # Снимаем только ранее добавленные нами file-хендлеры (на случай reload)
            for h in root.handlers[:]:
                if isinstance(h, RotatingFileHandler):
                    h.close()
                    root.removeHandler(h)
            fh = RotatingFileHandler(
                log_dir / "app.log", maxBytes=1024 * 1024, backupCount=3,
                encoding="utf-8", delay=True,
            )
            fh.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
            )
            root.addHandler(fh)
            _FILE_LOG_READY = True
            logging.info("Система логирования инициализирована.")

        # UI-handler привязан к конкретному ui.log этого клиента — пересоздаём,
        # сняв предыдущий, чтобы не плодить дубли при переоткрытии страницы.
        if self.el.get("logs"):
            for h in root.handlers[:]:
                if isinstance(h, NiceGuiLogHandler):
                    root.removeHandler(h)
            ui_handler = NiceGuiLogHandler(self.el["logs"], client_id=self._client_id)
            ui_handler.setFormatter(
                logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")
            )
            root.addHandler(ui_handler)

    def switch_to_tab(self, name: str):
        if self.tabs is not None:
            self.tabs.set_value(name)

    # ── прогресс-индикаторы ───────────────────────────────────────
    def _show_progress(self, label: str, *, key_progress: str = "letter_progress",
                       key_status: str = "letter_status") -> None:
        """Показывает прогресс-бар и статусный лейбл в текущей вкладке."""
        p = self.el.get(key_progress)
        s = self.el.get(key_status)
        if p:
            p.set_visibility(True)
        if s:
            s.set_text(label)
            s.set_visibility(True)

    def _hide_progress(self, *, key_progress: str = "letter_progress",
                       key_status: str = "letter_status") -> None:
        """Скрывает прогресс-бар и статусный лейбл."""
        p = self.el.get(key_progress)
        s = self.el.get(key_status)
        if p:
            p.set_visibility(False)
        if s:
            s.set_visibility(False)

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
            return "#a1a1aa"
        upper = s_max if s_max is not None else s_min
        lower = s_min if s_min is not None else s_max
        # Приглушённые сигналы, чтобы з/п не «светофорила» в таблице:
        # выше ожидания → мягкий зелёный, частично → нейтрально-светлый,
        # ниже → приглушённый красный (не алерт).
        if lower >= expectation:
            return "#6ee7b7"   # выше ожидания — спокойный мятный
        if upper >= expectation:
            return "#d4d4d8"   # в диапазоне — нейтральный светлый
        return "#a86b6b"       # ниже — тусклый красноватый, не кричит

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
