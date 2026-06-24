"""Кастомный чип-фильтр: кнопка с выпадающим меню, никакого Quasar select."""
from nicegui import ui


class FilterChip:
    """Компактная кнопка-чип с выпадающим списком вариантов.

    Имеет свойство .value (как ui.select) для совместимости с контроллером.
    Поддерживает single и multiple режимы.
    """

    def __init__(
        self,
        label: str,
        options: dict,           # {value: display_text}
        default=None,
        multiple: bool = False,
        on_change=None,
    ):
        self._label = label
        self._options = options   # dict value→label
        self._multiple = multiple
        self._on_change = on_change
        self._value = default if default is not None else ([] if multiple else None)

        self._btn_label: ui.label | None = None
        self._btn: ui.button | None = None
        self._count_badge: ui.label | None = None
        self._menu: ui.menu | None = None
        self._item_labels: dict = {}   # value → ui.label (для подсветки)

        self._render()

    # ── public API ────────────────────────────────────────────
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, v):
        self._value = v
        self._refresh_btn()

    # ── render ────────────────────────────────────────────────
    def _render(self):
        with ui.element("div").classes("vob-chip-wrap"):
            self._btn = ui.button(on_click=lambda: self._menu.open()).classes(
                "vob-chip-btn"
            ).props("no-caps flat dense")
            with self._btn:
                self._btn_label = ui.label("").classes("vob-chip-text")
                # Счётчик выбранного — фиксированный кружок, не двигает раскладку
                self._count_badge = ui.label("").classes("vob-chip-count")
                self._count_badge.set_visibility(False)
                ui.html('<span class="material-icons vob-chip-arrow">expand_more</span>')

            with ui.menu().classes("vob-chip-menu") as menu:
                self._menu = menu
                for val, text in self._options.items():
                    lbl = ui.label(text).classes("vob-chip-item")
                    lbl.on("click", lambda _, v=val: self._select(v))
                    self._item_labels[val] = lbl

        self._refresh_btn()

    def _select(self, val):
        if self._multiple:
            if isinstance(self._value, list):
                if val in self._value:
                    self._value = [x for x in self._value if x != val]
                else:
                    self._value = self._value + [val]
            else:
                self._value = [val]
        else:
            self._value = val
            self._menu.close()

        self._refresh_btn()
        self._refresh_items()
        if self._on_change:
            self._on_change()

    def _refresh_btn(self):
        if self._btn_label is None:
            return

        if self._multiple:
            sel = self._value or []
            active = bool(sel)
            # Текст чипа фиксирован названием фильтра — раскладка не прыгает.
            # Один выбор → показываем само значение; несколько → кружок с числом.
            if len(sel) == 1:
                text = self._options.get(sel[0], str(sel[0]))
                count = 0
            elif active:
                text = self._label
                count = len(sel)
            else:
                text = self._label
                count = 0
        else:
            active = self._value is not None and self._value in self._options
            text = self._options[self._value] if active else self._label
            count = 0

        self._btn_label.set_text(text)
        self._btn_label.classes(
            replace="vob-chip-text vob-chip-text--active" if active else "vob-chip-text"
        )

        # Кружок-счётчик (только когда выбрано >1 в мультирежиме)
        if self._count_badge is not None:
            if count > 1:
                self._count_badge.set_text(str(count))
                self._count_badge.set_visibility(True)
            else:
                self._count_badge.set_visibility(False)

        # Подсветка всей кнопки-чипа (фон/рамка), а не только текста.
        if self._btn is not None:
            self._btn.classes(
                replace="vob-chip-btn vob-chip-active" if active else "vob-chip-btn"
            )

    def _refresh_items(self):
        for val, lbl in self._item_labels.items():
            if self._multiple:
                selected = val in (self._value or [])
            else:
                selected = val == self._value
            if selected:
                lbl.classes(replace="vob-chip-item vob-chip-item--active")
            else:
                lbl.classes(replace="vob-chip-item")
