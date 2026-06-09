"""gui_ng.controller — обратная совместимость.

Реальная реализация перенесена в gui_ng.controllers (пакет с миксинами).
Все импорты вида ``from gui_ng.controller import AppController`` продолжают работать.
"""
from gui_ng.controllers import AppController, NiceGuiLogHandler  # noqa: F401

__all__ = ["AppController", "NiceGuiLogHandler"]
