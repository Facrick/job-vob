"""Общие вспомогательные виджеты для вкладок."""
from nicegui import ui


def _metric_card(label: str, value: str, icon: str, accent: str = "#a78bfa"):
    """Компактная карточка-метрика в стиле Fusion: иконка-чип + цифра + подпись.

    Возвращает (value_label, label_label) — обновляйте .set_text() для живых данных.
    """
    with ui.element("div").classes("vob-metric items-center no-wrap").style(
        f"--vob-accent:{accent};display:flex;gap:10px;flex:1 1 0;min-width:120px"
    ):
        with ui.element("div").classes("vob-metric-icon").style(
            f"--vob-accent:{accent}"
        ):
            ui.icon(icon).style(f"color:{accent};font-size:17px")
        with ui.column().classes("gap-0"):
            val = ui.label(value).classes("vob-metric-value")
            lbl = ui.label(label).classes("vob-metric-label")
    return val, lbl


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


def _split(value=58):
    """Горизонтальный сплиттер с грипом, заполняющий высоту вкладки."""
    sp = ui.splitter(value=value).classes("w-full").style("flex:1 1 0;min-height:0")
    with sp.separator:
        ui.element("div").classes("vob-grip")
    return sp
