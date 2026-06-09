"""gui_ng.controllers — AppController, собранный из миксинов по ответственности.

Структура:
  _base.py        — NiceGuiLogHandler, инициализация, ленивые сервисы, утилиты
  _scout.py       — CRM-вкладка: таблица, воронка, поиск
  _letters.py     — вкладка «Письма»: генерация, анализ, автоотклик, статус
  _hh.py          — интеграция с hh.ru: авторизация, синхронизация статусов
  _files.py       — нативные диалоги pywebview, загрузка резюме, экспорт
  _interview.py   — mock-собеседование и отчёт
  _analytics.py   — зарплатный график, хитмап навыков, журнал
  _handbook.py    — учебник, план обучения, упражнения
  _helpers.py     — служебные функции (_q, _sanitize_hh_html)

Используйте:
    from gui_ng.controllers import AppController
"""
from gui_ng.controllers._analytics import _AnalyticsMixin
from gui_ng.controllers._base import NiceGuiLogHandler, _AppControllerBase
from gui_ng.controllers._files import _FilesMixin
from gui_ng.controllers._handbook import _HandbookMixin
from gui_ng.controllers._hh import _HHMixin
from gui_ng.controllers._interview import _InterviewMixin
from gui_ng.controllers._letters import _LettersMixin
from gui_ng.controllers._scout import _ScoutMixin

__all__ = ["AppController", "NiceGuiLogHandler"]


class AppController(
    _HandbookMixin,
    _AnalyticsMixin,
    _InterviewMixin,
    _FilesMixin,
    _HHMixin,
    _LettersMixin,
    _ScoutMixin,
    _AppControllerBase,
):
    """Контроллер NiceGUI-приложения.

    Все методы реализованы в миксинах — см. gui_ng/controllers/*.py.
    Этот класс лишь собирает их вместе через множественное наследование.
    """
