"""VacancyList — список вакансий на чистом HTML без Quasar/NiceGUI-обёрток.

Шапка + строки генерируются в одном ui.html() блоке — один DOM-узел,
один CSS Grid, заголовки и ячейки гарантированно совпадают при любой ширине.
События делегируются на общий контейнер (event delegation).
"""
import html as _html
from collections.abc import Callable

from nicegui import ui

_COLUMNS = [
    ("match_num",  "Match",    "center"),
    ("company",    "Компания", "left"),
    ("title",      "Вакансия", "left"),
    ("salary_num", "З/п",      "left"),
    ("status_num", "Статус",   "center"),
]

_PER_PAGE_OPTIONS = [25, 50, 100, 0]


def _esc(s) -> str:
    return _html.escape(str(s or ""), quote=True)


class VacancyList:
    def __init__(
        self,
        *,
        on_row_click: Callable[[dict], None] | None = None,
        on_selection_change: Callable[[], None] | None = None,
    ):
        self._on_row_click = on_row_click
        self._on_selection_change = on_selection_change

        self._all: list[dict] = []
        self._sort_key: str = "match_num"
        self._sort_desc: bool = True
        self._page: int = 0
        self._per_page: int = 25
        self._selected_ids: set[str] = set()
        self._active_id: str | None = None

        # Внешний контейнер — flex-колонка на всю высоту карточки
        self._root = ui.element("div").classes("vob-vlist")
        with self._root:
            # Единый HTML-блок: шапка + строки в одном <div class="vob-vtable">
            # Пагинация — отдельно, там нужны Python-обработчики
            self._table_el = ui.html("", sanitize=False).classes("vob-vtable-wrap")
            # js_handler собирает нужные данные из DOM и отправляет в Python через emit().
            # DOMStringMap (dataset) сериализуем через Object.fromEntries — JSON-совместимо.
            self._table_el.on(
                "click",
                handler=lambda e: self._on_table_click(e.args),
                js_handler=(
                    "(event) => {"
                    "  const t = event.target;"
                    "  const p = t.parentElement;"
                    "  emit({"
                    "    tag: t.tagName || '',"
                    "    dataset: Object.fromEntries(Object.entries(t.dataset || {})),"
                    "    pDataset: p ? Object.fromEntries(Object.entries(p.dataset || {})) : {},"
                    "    pTag: p ? (p.tagName || '') : ''"
                    "  });"
                    "}"
                ),
            )
            self._table_el.on(
                "change",
                handler=lambda e: self._on_table_change(e.args),
                js_handler=(
                    "(event) => {"
                    "  const t = event.target;"
                    "  emit({"
                    "    tag: t.tagName || '',"
                    "    dataset: Object.fromEntries(Object.entries(t.dataset || {})),"
                    "    checked: t.checked"
                    "  });"
                    "}"
                ),
            )
            self._pager_el = ui.element("div").classes("vob-pager")
        self._render()

    # ── Публичный интерфейс ───────────────────────────────────────────────────

    @property
    def rows(self) -> list[dict]:
        return self._all

    @rows.setter
    def rows(self, value: list[dict]) -> None:
        self._all = list(value or [])
        present = {r["id"] for r in self._all}
        self._selected_ids &= present
        self._page = 0
        self._render()

    @property
    def selected(self) -> "_SelectedView":
        return _SelectedView(self)

    def update(self) -> None:
        self._render()

    def add_row(self, row: dict) -> None:
        if any(r["id"] == row["id"] for r in self._all):
            return
        self._all.append(row)
        self._render()

    def set_active(self, vid: str | None) -> None:
        if self._active_id == vid:
            return
        self._active_id = vid
        self._render()

    # ── Рендер ───────────────────────────────────────────────────────────────

    def _render(self) -> None:
        rows = self._sorted()
        pages = self._total_pages(len(rows))
        self._page = min(self._page, max(0, pages - 1))
        page_rows = self._page_slice(rows)
        page_ids = {r["id"] for r in page_rows}

        self._table_el.set_content(
            self._build_table_html(page_rows, page_ids)
        )
        self._render_pager(len(rows), pages)

    def _build_table_html(self, page_rows: list[dict], page_ids: set) -> str:
        all_selected = bool(page_ids) and page_ids <= self._selected_ids
        head_checked = "checked" if all_selected else ""

        # Заголовки
        head_cells = ""
        for key, label, align in _COLUMNS:
            arrow = (" ▼" if self._sort_desc else " ▲") if self._sort_key == key else ""
            head_cells += (
                f'<div class="vob-vhead-cell align-{align}" data-sort="{_esc(key)}">'
                f'{_esc(label)}{arrow}</div>'
            )

        head = (
            f'<div class="vob-vhead">'
            f'<input type="checkbox" class="vob-chk" data-role="select-all" {head_checked}>'
            f'{head_cells}'
            f'</div>'
        )

        # Строки
        if not self._all:
            body = '<div class="vob-vempty">Вакансий пока нет — запустите поиск выше.</div>'
        elif not page_rows:
            body = '<div class="vob-vempty">Ничего не найдено.</div>'
        else:
            body = "".join(self._row_html(r) for r in page_rows)

        return f'<div class="vob-vtable">{head}<div class="vob-vrows">{body}</div></div>'

    def _row_html(self, r: dict) -> str:
        vid     = _esc(r["id"])
        active  = " vob-vrow--active" if r["id"] == self._active_id else ""
        checked = "checked" if r["id"] in self._selected_ids else ""

        mcol   = _esc(r.get("match_color", "#71717a"))
        match  = _esc(r.get("match", "—"))
        comp   = _esc(r.get("company", ""))
        title  = _esc(r.get("title", ""))
        salary = _esc(r.get("salary", ""))
        scol   = _esc(r.get("salary_color", "#a1a1aa"))
        stcol  = _esc(r.get("status_color", "#71717a"))
        status = _esc(r.get("status", ""))

        # data-id на КАЖДОМ дочернем элементе — NiceGUI не передаёт
        # полное дерево DOM в e.args, поэтому ищем data-id прямо на target.
        # «Soft»-бейджи: полупрозрачный фон цвета + цветной текст + тонкая
        # обводка вместо сплошной заливки — не выжигают, цвет читается как сигнал.
        # {color}22 / {color}59 — hex-альфа (~13% фон, ~35% рамка).
        match_style = (
            f"background:{mcol}22;color:{mcol};"
            f"border:1px solid {mcol}59;font-weight:700"
        )
        status_style = (
            f"background:{stcol}22;color:{stcol};"
            f"border:1px solid {stcol}59;font-weight:600"
        )
        d = f'data-id="{vid}"'
        return (
            f'<div class="vob-vrow{active}" {d}>'
            f'<input type="checkbox" class="vob-chk" data-id="{vid}" {checked}>'
            f'<div class="vob-vc-center" {d}>'
            f'<span class="vob-badge" {d} style="{match_style}">{match}</span>'
            f'</div>'
            f'<div class="vob-vrow-company" {d}>{comp}</div>'
            f'<div class="vob-vrow-title" {d}>{title}</div>'
            f'<div class="vob-vrow-salary" {d} style="color:{scol}">{salary}</div>'
            f'<div class="vob-vc-center" {d}>'
            f'<span class="vob-badge" {d} style="{status_style}">{status}</span>'
            f'</div>'
            f'</div>'
        )

    # ── Обработчики событий таблицы ───────────────────────────────────────────

    def _on_table_click(self, args) -> None:
        # args приходит как dict от js_handler emit({tag, dataset, pDataset, pTag})
        if not isinstance(args, dict):
            return
        tag = (args.get("tag") or "").upper()
        dataset = args.get("dataset") or {}
        parent_dataset = args.get("pDataset") or {}

        if tag == "INPUT":
            return

        # Клик по заголовку сортировки
        sort_key = dataset.get("sort") or parent_dataset.get("sort")
        if sort_key:
            self._sort_by(sort_key)
            return

        # Клик по строке — открыть деталь
        vid = dataset.get("id") or parent_dataset.get("id")
        if vid:
            row = next((r for r in self._all if r["id"] == vid), None)
            if row:
                self._row_clicked(row)

    def _on_table_change(self, args) -> None:
        # args приходит как dict от js_handler emit({tag, dataset, checked})
        if not isinstance(args, dict):
            return
        tag = (args.get("tag") or "").upper()
        dataset = args.get("dataset") or {}
        checked = bool(args.get("checked", False))

        if tag != "INPUT":
            return
        role = dataset.get("role")
        if role == "select-all":
            # Получаем page_ids из текущего состояния
            rows = self._sorted()
            page_rows = self._page_slice(rows)
            page_ids = {r["id"] for r in page_rows}
            if checked:
                self._selected_ids |= page_ids
            else:
                self._selected_ids -= page_ids
            self._render()
            if self._on_selection_change:
                self._on_selection_change()
        else:
            vid = dataset.get("id")
            if vid:
                if checked:
                    self._selected_ids.add(vid)
                else:
                    self._selected_ids.discard(vid)
                if self._on_selection_change:
                    self._on_selection_change()

    def _find_row_id(self, target: dict) -> str | None:
        return (target.get("dataset") or {}).get("id")

    def _sort_by(self, key: str) -> None:
        if self._sort_key == key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = key.endswith("_num")
        self._page = 0
        self._render()

    def _row_clicked(self, row: dict) -> None:
        self.set_active(row["id"])
        if self._on_row_click:
            self._on_row_click(row)

    # ── Пагинация ─────────────────────────────────────────────────────────────

    def _render_pager(self, total: int, pages: int) -> None:
        if self._per_page == 0:
            shown_from, shown_to = (1 if total else 0), total
        else:
            shown_from = self._page * self._per_page + 1 if total else 0
            shown_to = min(total, (self._page + 1) * self._per_page)

        self._pager_el.clear()
        with self._pager_el:
            ui.label(f"{shown_from}–{shown_to} из {total}").classes("vob-pager-info")
            ui.element("div").classes("vob-pager-spacer")

            for opt in _PER_PAGE_OPTIONS:
                lbl = "Все" if opt == 0 else str(opt)
                cls = "vob-pager-size" + (" active" if opt == self._per_page else "")
                btn = ui.element("div").classes(cls)
                with btn:
                    ui.label(lbl)
                btn.on("click", lambda _, o=opt: self._set_per_page(o))

            prev_dis = self._page <= 0
            nav_prev = ui.element("div").classes("vob-pager-nav" + (" disabled" if prev_dis else ""))
            with nav_prev:
                ui.html('<span class="material-icons" style="font-size:18px">chevron_left</span>')
            if not prev_dis:
                nav_prev.on("click", lambda _: self._goto(self._page - 1))

            ui.label(f"{self._page + 1} / {pages}").classes("vob-pager-page")

            next_dis = self._page >= pages - 1
            nav_next = ui.element("div").classes("vob-pager-nav" + (" disabled" if next_dis else ""))
            with nav_next:
                ui.html('<span class="material-icons" style="font-size:18px">chevron_right</span>')
            if not next_dis:
                nav_next.on("click", lambda _: self._goto(self._page + 1))

    def _set_per_page(self, opt: int) -> None:
        self._per_page = opt
        self._page = 0
        self._render()

    def _goto(self, page: int) -> None:
        self._page = max(0, page)
        self._render()

    # ── Вспомогательное ───────────────────────────────────────────────────────

    def _sorted(self) -> list[dict]:
        key = self._sort_key
        def val(r):
            v = r.get(key)
            return v.lower() if isinstance(v, str) else (v if v is not None else -1)
        return sorted(self._all, key=val, reverse=self._sort_desc)

    def _page_slice(self, rows):
        if self._per_page == 0:
            return rows
        s = self._page * self._per_page
        return rows[s:s + self._per_page]

    def _total_pages(self, n):
        if self._per_page == 0:
            return 1
        return max(1, (n + self._per_page - 1) // self._per_page)


class _SelectedView:
    def __init__(self, owner: VacancyList):
        self._owner = owner

    def _rows(self):
        ids = self._owner._selected_ids
        return [r for r in self._owner._all if r["id"] in ids]

    def __iter__(self):
        return iter(self._rows())

    def __len__(self):
        return len(self._owner._selected_ids)

    def __bool__(self):
        return bool(self._owner._selected_ids)

    def clear(self) -> None:
        self._owner._selected_ids.clear()
        self._owner._render()
