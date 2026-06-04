"""theme.py — палитра и общие UI-хелперы для NiceGUI-версии интерфейса.

Тёмная тема с индиго-акцентом (как во Flet-версии), но рендер через Quasar/Vue,
поэтому выглядит современнее «из коробки».
"""

from nicegui import ui

# ── Палитра (hex для Quasar) ───────────────────────────────────
PRIMARY = "#5C6BC0"   # indigo-400
SURFACE = "#1e1f26"   # фон карточек
BG = "#16171c"        # фон страницы
MUTED = "#9aa0b4"     # вторичный текст

# Цвета статусов воронки → (подпись, hex).
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "discovered": ("Новая", "#42a5f5"),
    "processed": ("Письмо", "#5c6bc0"),
    "applied": ("Отклик", "#ff8f00"),
    "interview": ("Интервью", "#ab47bc"),
    "offer": ("Оффер", "#66bb6a"),
    "rejected": ("Отказ", "#ef5350"),
}

GRADE_HEX = {"Junior": "#64b5f6", "Middle": "#5c6bc0", "Senior/Lead": "#ab47bc"}


def apply_theme() -> None:
    """Включает тёмный режим и задаёт фирменные цвета Quasar."""
    ui.dark_mode().enable()
    ui.colors(
        primary=PRIMARY,
        secondary="#7986cb",
        accent="#ab47bc",
        positive="#66bb6a",
        negative="#ef5350",
        warning="#ff8f00",
        dark=SURFACE,
        dark_page=BG,
    )
    # Глобальная подстройка: карточки, фон, тонкие скроллбары, разделитель сплиттера.
    ui.add_head_html(
        """
        <style>
          body { background-color: #16171c; }
          .q-card { border-radius: 14px; }
          .vob-muted { color: #9aa0b4; }
          /* Скролл появляется только при необходимости и выглядит ненавязчиво.
             overflow-x:hidden убирает паразитный горизонтальный скролл под панелями. */
          .vob-scroll { overflow-y: auto; overflow-x: hidden; min-height: 0; }
          /* Панели сплиттера сами не скроллятся — это делает .vob-scroll внутри. */
          .q-splitter__panel { overflow: hidden; }
          ::-webkit-scrollbar { width: 9px; height: 9px; }
          ::-webkit-scrollbar-thumb { background: #3a3b44; border-radius: 5px; }
          ::-webkit-scrollbar-thumb:hover { background: #4a4b56; }
          ::-webkit-scrollbar-track { background: transparent; }
          /* Разделитель сплиттера: невидимая зона захвата + грип строго по центру. */
          .q-splitter__separator {
            background: transparent !important; width: 12px !important;
            display: flex !important; align-items: center; justify-content: center;
          }
          .vob-grip {
            width: 4px; height: 40px; border-radius: 3px;
            background: #5C6BC0; opacity: .35; transition: opacity .15s;
          }
          .q-splitter__separator:hover .vob-grip { opacity: .8; }
          /* Текстовые поля, которые должны заполнять высоту панели (письма/редактор). */
          .vob-fill, .vob-fill .q-field__control, .vob-fill .q-field__control textarea {
            height: 100% !important;
          }
          .vob-fill .q-field__control textarea { resize: none; }
          /* Пузыри чата собеседования: ИИ (слева, сланцевый) и вы (справа, индиго).
             Цвет форсируем и на контейнере, и на вложенном контенте — иначе тёмный
             текст Quasar остаётся нечитаемым на тёмном фоне. */
          .q-message-text,
          .q-message-text-content,
          .q-message-text > div {
            color: #ffffff !important;
          }
          .q-message-text {
            background: #2f3650 !important;
            line-height: 1.55; padding: 9px 13px; border-radius: 12px;
          }
          .q-message-text--sent {
            background: #4150a0 !important;
          }
          /* Хвостик пузыря — в цвет фона, чтобы не было серого артефакта. */
          .q-message-text:last-child:before { border-bottom-color: #2f3650 !important; }
          .q-message-text--sent:last-child:before { border-bottom-color: #4150a0 !important; }
          .q-message-name { color: #c2c8e0 !important; font-weight: 600; font-size: .8rem; }
          .q-message-stamp { color: #9aa0b4 !important; }
          /* Заголовки внутри материала учебника не должны «съедать» высоту. */
          .nicegui-markdown h1 { font-size: 1.25rem; margin: .4em 0 .3em; }
          .nicegui-markdown h2 { font-size: 1.1rem;  margin: .4em 0 .3em; }
          .nicegui-markdown h3 { font-size: 1rem;    margin: .3em 0 .2em; }
          /* Читаемая типографика: абзацы, списки, межстрочный интервал. */
          .nicegui-markdown p { margin: .5em 0; line-height: 1.55; }
          .nicegui-markdown ul, .nicegui-markdown ol { margin: .4em 0; padding-left: 1.25em; }
          .nicegui-markdown li { margin: .15em 0; line-height: 1.5; }
          .nicegui-markdown code { background: #ffffff14; padding: 1px 5px; border-radius: 4px; }
          /* Сегментированный переключатель режимов учебника — без обрезки подписей. */
          .q-btn-toggle .q-btn__content { white-space: nowrap; }
          /* Сайдбар в свёрнутом состоянии: только иконки. */
          .vob-rail.vob-collapsed { width: 64px !important; min-width: 64px !important; }
          .vob-rail.vob-collapsed .vob-rail-hide { display: none !important; }
          .vob-rail.vob-collapsed .q-tab__label { display: none !important; }
          .vob-rail.vob-collapsed .q-tab { justify-content: center !important; }
          /* Таблица вакансий с перетаскиваемыми границами колонок. */
          .vob-table table { table-layout: fixed; }
          .vob-table th, .vob-table td {
            overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
          }
          .vob-col-resizer {
            position: absolute; top: 0; right: 0; width: 6px; height: 100%;
            cursor: col-resize; user-select: none; z-index: 2;
          }
          .vob-col-resizer:hover { background: #5C6BC055; }
        </style>
        """
    )
    # Скрипт: вешает «ручки» на заголовки таблицы .vob-table и тянет ширину колонок.
    ui.add_body_html(
        """
        <script>
        function vobInitColResize() {
          document.querySelectorAll('.vob-table thead tr th').forEach(function (th) {
            if (th.querySelector('.vob-col-resizer')) return;
            th.style.position = 'relative';
            var handle = document.createElement('div');
            handle.className = 'vob-col-resizer';
            th.appendChild(handle);
            handle.addEventListener('click', function (e) { e.stopPropagation(); });
            handle.addEventListener('mousedown', function (e) {
              var startX = e.pageX, startW = th.offsetWidth;
              function onMove(ev) {
                var w = Math.max(48, startW + (ev.pageX - startX));
                th.style.width = w + 'px';
              }
              function onUp() {
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                document.body.style.userSelect = '';
              }
              document.addEventListener('mousemove', onMove);
              document.addEventListener('mouseup', onUp);
              document.body.style.userSelect = 'none';
              e.preventDefault(); e.stopPropagation();
            });
          });
        }
        new MutationObserver(vobInitColResize).observe(
          document.body, { childList: true, subtree: true }
        );
        document.addEventListener('DOMContentLoaded', vobInitColResize);
        setInterval(vobInitColResize, 1500);
        </script>
        """
    )


def match_color(score) -> str:
    if score is None:
        return MUTED
    score = int(score)
    if score >= 70:
        return "#66bb6a"
    if score >= 40:
        return "#ff8f00"
    return "#ef5350"
