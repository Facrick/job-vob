"""theme.py — дизайн-система приложения (shadcn/Vercel-стиль).

Тёмная тема на базе zinc-950, glassmorphism-карточки, шрифт Inter,
один фиолетовый акцент. Минимум декора — максимум читаемости.
"""

from nicegui import ui

# ── Дизайн-токены ───────────────────────────────────────────────
PRIMARY   = "#a78bfa"   # violet-400  — единственный акцент
SURFACE   = "#18181b"   # zinc-900    — фон карточек
BG        = "#09090b"   # zinc-950    — фон страницы
BORDER    = "#27272a"   # zinc-800    — границы
MUTED     = "#71717a"   # zinc-500    — вторичный текст
TEXT      = "#fafafa"   # zinc-50     — основной текст

# Статусы воронки → (подпись, hex)
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "discovered": ("Новая",    "#60a5fa"),   # blue-400
    "processed":  ("Письмо",   "#a78bfa"),   # violet-400
    "applied":    ("Отклик",   "#fb923c"),   # orange-400
    "interview":  ("Интервью", "#c084fc"),   # purple-400
    "offer":      ("Оффер",    "#4ade80"),   # green-400
    "rejected":   ("Отказ",    "#f87171"),   # red-400
}

GRADE_HEX = {
    "Junior":      "#60a5fa",
    "Middle":      "#a78bfa",
    "Senior/Lead": "#c084fc",
}


def apply_theme() -> None:
    """Применяет shadcn/Vercel тёмную тему к Quasar."""
    ui.dark_mode().enable()
    ui.colors(
        primary=PRIMARY,
        secondary="#7c3aed",
        accent="#c084fc",
        positive="#4ade80",
        negative="#f87171",
        warning="#fb923c",
        dark=SURFACE,
        dark_page=BG,
    )

    # Загрузка Inter из Google Fonts (weight 400/500/600/700)
    ui.add_head_html(
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"'
        ' rel="stylesheet">'
    )

    ui.add_head_html("""
<style>
  /* ── Базовый сброс и типографика ──────────────────────── */
  *, *::before, *::after { box-sizing: border-box; }

  body {
    background-color: #09090b;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    font-size: 14px;
    color: #fafafa;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Скроллбары ───────────────────────────────────────── */
  ::-webkit-scrollbar              { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track        { background: transparent; }
  ::-webkit-scrollbar-thumb        { background: #3f3f46; border-radius: 99px; }
  ::-webkit-scrollbar-thumb:hover  { background: #52525b; }

  /* ── Карточки: glassmorphism ──────────────────────────── */
  .q-card {
    background: rgba(24, 24, 27, 0.85) !important;
    backdrop-filter: blur(12px) saturate(120%);
    -webkit-backdrop-filter: blur(12px) saturate(120%);
    border: 1px solid rgba(255, 255, 255, 0.06) !important;
    border-radius: 8px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,.4), 0 0 0 1px rgba(255,255,255,.03) !important;
  }

  /* ── Layout-хелперы ───────────────────────────────────── */
  .vob-muted  { color: #71717a !important; }
  .vob-scroll { overflow-y: auto; overflow-x: hidden; min-height: 0; }
  .q-splitter__panel { overflow: hidden; }

  /* ── Сайдбар ──────────────────────────────────────────── */
  .vob-rail.vob-collapsed { width: 60px !important; min-width: 60px !important; }
  .vob-rail.vob-collapsed .vob-rail-hide  { display: none !important; }
  .vob-rail.vob-collapsed .q-tab__label   { display: none !important; }
  .vob-rail.vob-collapsed .q-tab          { justify-content: center !important; }

  /* Вкладки сайдбара */
  .q-tab {
    border-radius: 6px !important;
    margin: 1px 6px !important;
    padding: 0 10px !important;
    min-height: 38px !important;
    transition: background .12s, color .12s !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #a1a1aa !important;
  }
  .q-tab:hover:not(.q-tab--active) {
    background: rgba(255,255,255,0.04) !important;
    color: #fafafa !important;
  }
  .q-tab--active {
    background: rgba(167, 139, 250, 0.12) !important;
    color: #a78bfa !important;
  }
  .q-tab__indicator { display: none !important; }

  /* ── Tab-panels контент ───────────────────────────────── */
  .q-tab-panel  { background: #09090b !important; }
  .q-tab-panels { background: #09090b !important; }

  /* ── Разделитель сплиттера ────────────────────────────── */
  .q-splitter__separator {
    background: transparent !important;
    width: 10px !important;
    display: flex !important;
    align-items: center;
    justify-content: center;
  }
  .vob-grip {
    width: 3px; height: 32px; border-radius: 99px;
    background: #a78bfa; opacity: .2; transition: opacity .15s;
  }
  .q-splitter__separator:hover .vob-grip { opacity: .6; }

  /* ── Кнопки ───────────────────────────────────────────── */
  .q-btn {
    border-radius: 6px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    letter-spacing: 0 !important;
    text-transform: none !important;
    transition: background .12s, opacity .12s !important;
  }
  .q-btn.bg-primary { box-shadow: 0 0 0 1px rgba(167,139,250,.3) !important; }
  .q-btn.bg-primary:hover { opacity: .88 !important; }
  .q-btn--outline {
    border-color: #3f3f46 !important;
    color: #a1a1aa !important;
  }
  .q-btn--outline:hover {
    border-color: #a78bfa !important;
    color: #a78bfa !important;
    background: rgba(167,139,250,.06) !important;
  }
  .q-btn--flat:hover { background: rgba(255,255,255,0.05) !important; }

  /* Переключатель режимов учебника */
  .q-btn-toggle .q-btn__content { white-space: nowrap; }
  .q-btn-toggle .q-btn {
    background: transparent !important;
    border-color: #3f3f46 !important;
    color: #71717a !important;
  }
  .q-btn-toggle .q-btn.q-btn--active,
  .q-btn-toggle .q-btn[aria-pressed="true"] {
    background: rgba(167,139,250,.15) !important;
    color: #a78bfa !important;
    border-color: rgba(167,139,250,.4) !important;
  }

  /* ── Поля ввода ───────────────────────────────────────── */
  .q-field__control {
    background: rgba(24,24,27,0.6) !important;
    border-radius: 6px !important;
  }
  .q-field--outlined .q-field__control::before {
    border-color: #3f3f46 !important;
    border-radius: 6px !important;
    transition: border-color .12s !important;
  }
  .q-field--outlined.q-field--focused .q-field__control::before,
  .q-field--outlined:hover .q-field__control::before {
    border-color: #a78bfa !important;
  }
  .q-field__label  { color: #71717a !important; font-size: 13px !important; }
  .q-field__native,
  .q-field__input  { color: #fafafa !important;  font-size: 13px !important; }
  .q-field--filled .q-field__control { background: rgba(39,39,42,0.5) !important; }

  /* ── Таблица вакансий ─────────────────────────────────── */
  .vob-table table {
    table-layout: fixed;
    border-collapse: separate;
    border-spacing: 0;
  }
  .vob-table thead th {
    background: rgba(18, 18, 18, 0.98) !important;
    color: #71717a !important;
    font-size: 11px !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: .05em !important;
    border-bottom: 1px solid #27272a !important;
    padding: 8px 10px !important;
  }
  .vob-table tbody tr {
    transition: background .1s !important;
  }
  .vob-table tbody tr:hover { background: rgba(167,139,250,0.04) !important; }
  .vob-table tbody td {
    font-size: 13px !important;
    padding: 7px 10px !important;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    border-bottom: 1px solid rgba(255,255,255,0.03) !important;
  }
  /* Ресайз-хэндл колонок */
  .vob-col-resizer {
    position: absolute; top: 0; right: 0;
    width: 4px; height: 100%;
    cursor: col-resize; user-select: none; z-index: 2;
    opacity: 0; transition: opacity .15s;
  }
  .vob-table thead th:hover .vob-col-resizer {
    opacity: 1;
    background: rgba(167,139,250,.4);
  }

  /* ── Чат интервью ─────────────────────────────────────── */
  .q-message-text,
  .q-message-text-content,
  .q-message-text > div { color: #fafafa !important; }
  .q-message-text {
    background: rgba(39,39,42,0.8) !important;
    backdrop-filter: blur(8px);
    border: 1px solid rgba(255,255,255,0.06) !important;
    border-radius: 10px !important;
    line-height: 1.55;
    padding: 9px 13px;
  }
  .q-message-text--sent {
    background: rgba(109, 40, 217, 0.22) !important;
    border-color: rgba(167,139,250,0.18) !important;
  }
  .q-message-text:last-child::before       { border-bottom-color: transparent !important; }
  .q-message-text--sent:last-child::before { border-bottom-color: transparent !important; }
  .q-message-name  { color: #a1a1aa !important; font-weight: 600; font-size: .78rem; }
  .q-message-stamp { color: #52525b !important; font-size: .72rem; }

  /* ── Markdown (учебник) ───────────────────────────────── */
  .nicegui-markdown { line-height: 1.6; }
  .nicegui-markdown h1 { font-size: 1.2rem;  font-weight: 700; margin: .6em 0 .3em;  color: #fafafa; }
  .nicegui-markdown h2 { font-size: 1.05rem; font-weight: 600; margin: .5em 0 .25em; color: #e4e4e7; }
  .nicegui-markdown h3 { font-size: .95rem;  font-weight: 600; margin: .4em 0 .2em;  color: #d4d4d8; }
  .nicegui-markdown p  { margin: .45em 0; color: #d4d4d8; }
  .nicegui-markdown ul,
  .nicegui-markdown ol { margin: .4em 0; padding-left: 1.3em; color: #d4d4d8; }
  .nicegui-markdown li { margin: .12em 0; line-height: 1.55; }
  .nicegui-markdown code {
    background: rgba(167,139,250,0.1);
    border: 1px solid rgba(167,139,250,0.15);
    padding: 1px 6px; border-radius: 4px;
    font-size: .85em; color: #c4b5fd;
  }
  .nicegui-markdown pre {
    background: #18181b;
    border: 1px solid #27272a;
    border-radius: 8px; padding: 12px 14px;
    overflow-x: auto; margin: .6em 0;
  }
  .nicegui-markdown pre code {
    background: transparent; border: none; padding: 0; color: #e4e4e7;
  }
  .nicegui-markdown strong { color: #fafafa; }
  .nicegui-markdown a {
    color: #a78bfa;
    text-decoration: underline;
    text-underline-offset: 2px;
  }
  .nicegui-markdown blockquote {
    border-left: 3px solid #a78bfa;
    margin: .5em 0; padding: .3em .8em;
    background: rgba(167,139,250,0.05);
    border-radius: 0 6px 6px 0;
    color: #a1a1aa;
  }

  /* ── Separator ────────────────────────────────────────── */
  .q-separator { background: #27272a !important; opacity: .7 !important; }

  /* ── Expansion ────────────────────────────────────────── */
  .q-expansion-item__container > .q-item:hover {
    background: rgba(255,255,255,.03) !important;
    border-radius: 6px !important;
  }
  .q-item__label { font-size: 13px !important; }

  /* ── Badges ───────────────────────────────────────────── */
  .q-badge {
    border-radius: 5px !important;
    font-size: 11px !important;
    font-weight: 600 !important;
  }

  /* ── Tooltip ──────────────────────────────────────────── */
  .q-tooltip {
    background: #27272a !important;
    color: #fafafa !important;
    border: 1px solid #3f3f46 !important;
    border-radius: 6px !important;
    font-size: 12px !important;
    font-family: 'Inter', sans-serif !important;
  }

  /* ── Spinner ──────────────────────────────────────────── */
  .q-spinner { color: #a78bfa !important; }

  /* ── Progress bar ─────────────────────────────────────── */
  .q-linear-progress__track { background: #27272a !important; }

  /* ── Select / Menu ────────────────────────────────────── */
  .q-menu {
    background: #18181b !important;
    border: 1px solid #27272a !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,.6) !important;
  }
  .q-item { color: #d4d4d8 !important; border-radius: 4px !important; }
  .q-item:hover { background: rgba(255,255,255,.05) !important; }
  .q-item--active { color: #a78bfa !important; }

  /* ── Chip ─────────────────────────────────────────────── */
  .q-chip {
    background: rgba(39,39,42,0.7) !important;
    border: 1px solid #3f3f46 !important;
    border-radius: 99px !important;
    color: #a1a1aa !important;
    font-size: 12px !important;
  }

  /* ── TextField fill helper ────────────────────────────── */
  .vob-fill, .vob-fill .q-field__control, .vob-fill .q-field__control textarea {
    height: 100% !important;
  }
  .vob-fill .q-field__control textarea { resize: none; }
</style>
""")

    # JS: drag-resize колонок таблицы
    ui.add_body_html("""
<script>
function vobInitColResize() {
  document.querySelectorAll('.vob-table thead tr th').forEach(function(th) {
    if (th.querySelector('.vob-col-resizer')) return;
    th.style.position = 'relative';
    var handle = document.createElement('div');
    handle.className = 'vob-col-resizer';
    th.appendChild(handle);
    handle.addEventListener('click', function(e) { e.stopPropagation(); });
    handle.addEventListener('mousedown', function(e) {
      var startX = e.pageX, startW = th.offsetWidth;
      function onMove(ev) {
        th.style.width = Math.max(48, startW + (ev.pageX - startX)) + 'px';
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
new MutationObserver(vobInitColResize).observe(document.body, {childList:true, subtree:true});
document.addEventListener('DOMContentLoaded', vobInitColResize);
setInterval(vobInitColResize, 1500);
</script>
""")


def match_color(score) -> str:
    if score is None:
        return MUTED
    score = int(score)
    if score >= 70:
        return "#4ade80"
    if score >= 40:
        return "#fb923c"
    return "#f87171"
