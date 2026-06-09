"""gui_ng.views — построение UI вкладок.

Каждая build_*_tab(c) создаёт NiceGUI-элементы и кладёт их в c.el[...],
откуда контроллер читает значения и обновляет содержимое. Бизнес-логики нет.
"""
from gui_ng.views.analytics import build_analytics_tab
from gui_ng.views.handbook import build_handbook_tab
from gui_ng.views.interview import build_interview_tab
from gui_ng.views.letters import build_letters_tab
from gui_ng.views.logs import build_logs_tab
from gui_ng.views.scout import build_scout_tab

__all__ = [
    "build_scout_tab",
    "build_letters_tab",
    "build_interview_tab",
    "build_analytics_tab",
    "build_handbook_tab",
    "build_logs_tab",
]
