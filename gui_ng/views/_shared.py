"""Общие вспомогательные виджеты для вкладок."""
from nicegui import ui


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
