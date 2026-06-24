"""Общие вспомогательные виджеты для вкладок."""
from nicegui import ui

# Декоративный спарклайн для KPI-карточек: мягкая «волна», просто намёк на тренд.
# Это не реальные данные — у нас нет временного ряда по каждой метрике;
# линия задаёт визуальный ритм карточки как в референсе.
_SPARK_POINTS = "0,20 14,15 28,17 42,9 56,12 70,5 84,8 98,3"


def _sparkline_svg(accent: str) -> str:
    """SVG-спарклайн с градиентной заливкой под линией (без JS-библиотек)."""
    gid = f"g{abs(hash(accent)) % 100000}"
    return f"""
    <svg class="vob-kpi-spark" viewBox="0 0 98 24" preserveAspectRatio="none">
      <defs>
        <linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{accent}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="{accent}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <polygon points="0,24 {_SPARK_POINTS} 98,24" fill="url(#{gid})"/>
      <polyline points="{_SPARK_POINTS}" fill="none"
        stroke="{accent}" stroke-width="1.8"
        stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """


def _metric_card(label: str, value: str, icon: str, accent: str = "#a78bfa"):
    """KPI-карточка: иконка слева + подпись/число справа + спарклайн в углу."""
    with ui.element("div").classes("vob-kpi").style(f"--vob-accent:{accent}"):
        with ui.element("div").classes("vob-kpi-icon"):
            ui.icon(icon).style(f"color:{accent};font-size:22px")
        with ui.element("div").classes("vob-kpi-text"):
            lbl = ui.label(label).classes("vob-kpi-label")
            val = ui.label(value).classes("vob-kpi-value")
        ui.html(_sparkline_svg(accent))
    return val, lbl


def _section_head(icon: str, title: str, accent: str = "#a78bfa"):
    """Хедер секции: цветная иконка-плашка + заголовок (стиль референса).
    Возвращает row — вызывающий может дописать кнопки/селекты справа."""
    row = ui.row().classes("w-full items-center gap-2 no-wrap")
    with row:
        with ui.element("div").classes("vob-sec-icon").style(f"--vob-accent:{accent}"):
            ui.icon(icon)
        ui.label(title).classes("text-base font-semibold")
    return row


def _card(extra=""):
    """Карточка-контейнер: flex-колонка, не переносит контент, со скруглением."""
    return ui.card().classes(f"w-full no-wrap overflow-hidden {extra}").props(
        "flat bordered"
    )


def _scroll(extra=""):
    """Прокручиваемая колонка: полоса появляется только при переполнении."""
    return ui.column().classes(f"w-full vob-scroll {extra}").style(
        "flex:1 1 0;min-height:0"
    )


def _split(value=58, height: str | None = None):
    """Горизонтальный сплиттер с грипом.

    По умолчанию заполняет высоту вкладки (flex:1 1 0). Если задан height
    (например "440px"), берёт фиксированную высоту — нужно внутри прокручиваемого
    контейнера, где flex-растягивание схлопнуло бы панели в ноль.
    """
    style = f"height:{height};flex:0 0 auto" if height else "flex:1 1 0;min-height:0"
    sp = ui.splitter(value=value).classes("w-full").style(style)
    with sp.separator:
        ui.element("div").classes("vob-grip")
    return sp
