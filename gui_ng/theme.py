"""theme.py — дизайн-система приложения (shadcn/Vercel-стиль).

Тёмная тема на базе zinc-950, glassmorphism-карточки, шрифт Inter,
один фиолетовый акцент. Минимум декора — максимум читаемости.
"""

from nicegui import ui

# ── Дизайн-токены (Aurora dark) ─────────────────────────────────
# Дуальный акцент: фиолет — основной (навигация, статусы, выделение),
# оранж — энергия (графики, тренды, CTA). Градиент оранж→фиолет — фирменный.
PRIMARY   = "#a78bfa"   # violet-400  — основной акцент
ACCENT     = "#fb7a3c"  # orange-400  — второй акцент (графики, тренды, CTA)
GRAD       = "linear-gradient(135deg, #fb7a3c 0%, #a78bfa 100%)"  # фирменный градиент
SURFACE   = "#141419"   # карточка (сплошная, чуть синее чёрного)
SURFACE_2 = "#1b1b22"   # вложенные элементы / hover
BG        = "#0a0a0f"   # фон страницы
BORDER    = "#26262f"   # границы
MUTED     = "#71717a"   # вторичный текст
TEXT      = "#fafafa"   # основной текст

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
  body, body * { user-select: text !important; -webkit-user-select: text !important; }
  .q-btn, .q-btn *, .vob-col-resizer { user-select: none !important; -webkit-user-select: none !important; }

  body {
    background-color: #0a0a0f;
    font-family: 'Inter', system-ui, -apple-system, sans-serif;
    font-size: 14px;
    color: #fafafa;
    -webkit-font-smoothing: antialiased;
  }

  /* ── Фоновое свечение по краям (Aurora) ──────────────────
     Тёплое оранжевое слева-внизу + холодное фиолетовое справа-вверху.
     Как на референсе: глубина без отвлечения. fixed → не скроллится. */
  body::before {
    content: "";
    position: fixed; inset: 0; z-index: 0; pointer-events: none;
    background:
      radial-gradient(50% 45% at 100% 0%,   rgba(139, 92, 246, .26) 0%, transparent 62%),
      radial-gradient(60% 55% at -8% 112%,   rgba(251, 122, 60, .16) 0%, transparent 60%),
      radial-gradient(45% 40% at 55% 118%,   rgba(167, 139, 250, .1) 0%, transparent 55%);
  }
  /* Свечение живёт ПОД контентом и сайдбаром (z-index:0), но сайдбар
     полупрозрачен лишь сверху — гарантируем, что под ним фон сплошной,
     чтобы свечение не давало резкую полосу в углу. */
  .vob-rail::after {
    content: ""; position: absolute; inset: 0; z-index: -1;
    background: #0e0e13;
  }
  /* Контент над свечением */
  #app, .q-layout { position: relative; z-index: 1; }

  /* ── Фирменные утилиты градиента ─────────────────────────── */
  .vob-grad-text {
    background: linear-gradient(135deg, #fb7a3c 0%, #a78bfa 100%);
    -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: transparent;
  }
  .vob-grad-bar {
    background: linear-gradient(180deg, #fb7a3c 0%, #a78bfa 100%) !important;
  }
  .vob-grad-bar-h {
    background: linear-gradient(90deg, #fb7a3c 0%, #a78bfa 100%) !important;
  }

  /* ── Скроллбары (overlay-стиль, с воздухом от края) ──────
     Дорожка шире (14px), но видимая часть thumb — узкая полоска
     по центру: прозрачный border + background-clip:padding-box даёт
     зазор от края, поэтому скролл не «прилипает» к контенту/карточкам. */
  * { scrollbar-width: thin; scrollbar-color: #3f3f46 transparent; }
  ::-webkit-scrollbar              { width: 14px; height: 14px; }
  ::-webkit-scrollbar-track        { background: transparent; }
  ::-webkit-scrollbar-thumb {
    background: #3f3f46;
    border-radius: 99px;
    border: 4px solid transparent;
    background-clip: padding-box;
    min-height: 40px;
  }
  ::-webkit-scrollbar-thumb:hover {
    background: #5a5a64;
    background-clip: padding-box;
  }
  ::-webkit-scrollbar-corner { background: transparent; }

  /* ── Карточки: стеклянные (Aurora) ────────────────────── */
  /* Полупрозрачный фон + blur — фоновое свечение просвечивает сквозь
     карточку, как на референсе. Не сплошная заливка. */
  .q-card {
    position: relative;
    background: rgba(20, 20, 25, 0.66) !important;
    backdrop-filter: blur(16px) saturate(1.1);
    -webkit-backdrop-filter: blur(16px) saturate(1.1);
    border: 1px solid rgba(255, 255, 255, 0.07) !important;
    border-radius: 14px !important;
    box-shadow:
      0 1px 3px rgba(0,0,0,.4),
      0 8px 28px -12px rgba(0,0,0,.5) !important;
  }
  /* Тонкая фирменная кромка сверху — еле заметный «дорогой» штрих */
  .q-card::before {
    content: ""; position: absolute; inset: 0 0 auto 0; height: 1px;
    border-radius: 14px 14px 0 0; pointer-events: none;
    background: linear-gradient(90deg,
      transparent 0%, rgba(251,122,60,.35) 30%,
      rgba(167,139,250,.45) 70%, transparent 100%);
    opacity: .6;
  }

  /* ── Иконка-плашка в хедере секции (стиль референса) ─────── */
  .vob-sec-icon {
    width: 30px; height: 30px; border-radius: 9px; flex: 0 0 auto;
    display: flex; align-items: center; justify-content: center;
    background: color-mix(in srgb, var(--vob-accent, #a78bfa) 18%, transparent);
    border: 1px solid color-mix(in srgb, var(--vob-accent, #a78bfa) 30%, transparent);
  }
  .vob-sec-icon .material-icons {
    color: var(--vob-accent, #a78bfa); font-size: 18px;
  }

  /* ── KPI-карточка ────────────────────────────────────────── */
  .vob-kpi {
    position: relative; overflow: hidden;
    display: flex; flex-direction: row; align-items: center; gap: 10px;
    flex: 1 1 145px; min-width: 140px;
    padding: 12px 14px;
    border-radius: 14px;
    background: #141419;
    border: 1px solid #26262f;
    box-shadow: 0 1px 4px rgba(0,0,0,.45);
    transition: border-color .14s, box-shadow .14s;
    cursor: default;
  }
  .vob-kpi:hover {
    border-color: color-mix(in srgb, var(--vob-accent, #a78bfa) 50%, #26262f);
    box-shadow: 0 4px 20px -6px rgba(0,0,0,.6);
  }
  .vob-kpi-icon {
    width: 38px; height: 38px; border-radius: 11px; flex: 0 0 auto;
    display: flex; align-items: center; justify-content: center;
    background: color-mix(in srgb, var(--vob-accent, #a78bfa) 20%, transparent);
  }
  .vob-kpi-icon .material-icons { color: var(--vob-accent, #a78bfa); font-size: 20px; }
  .vob-kpi-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1 1 0; }
  .vob-kpi-label {
    font-size: 10px; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; color: #71717a; line-height: 1.2;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .vob-kpi-value {
    font-size: 24px; font-weight: 800; line-height: 1.1; color: #fafafa;
    font-variant-numeric: tabular-nums;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  /* Спарклайн — правый нижний угол */
  .vob-kpi-spark {
    position: absolute; right: 0; bottom: 0;
    width: 80px; height: 36px; pointer-events: none;
  }

  /* ── VacancyList ── */

  .vob-vlist {
    display: flex; flex-direction: column;
    width: 100%; height: 100%; min-height: 0; overflow: hidden;
  }
  /* NiceGUI оборачивает ui.html() в div — растягиваем эту обёртку */
  .vob-vtable-wrap,
  .vob-vtable-wrap > div {
    flex: 1 1 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden;
  }
  /* Главный блок: шапка + строки.
     --vob-grid задаётся здесь и применяется к .vob-vhead и .vob-vrow напрямую —
     оба элемента живут внутри .vob-vtable, поэтому переменная гарантированно одна. */
  .vob-vtable {
    display: flex; flex-direction: column;
    flex: 1 1 0; min-height: 0; overflow: hidden;
    --vob-grid: 30px 58px 1fr 1.4fr 118px 88px;
    --vob-px: 12px;
  }
  .vob-vhead {
    display: grid; grid-template-columns: var(--vob-grid);
    align-items: center; column-gap: 12px;
    padding: 6px var(--vob-px) 8px var(--vob-px);
    border-bottom: 1px solid #26262f;
    font-size: 11px; font-weight: 600; letter-spacing: .03em;
    text-transform: uppercase; color: #8b8b96;
    flex: 0 0 auto;
  }
  .vob-vhead-cell {
    cursor: pointer; white-space: nowrap;
    overflow: hidden; text-overflow: ellipsis;
    transition: color .12s;
  }
  .vob-vhead-cell:hover { color: #c4b5fd; }
  .vob-vhead-cell.align-center { text-align: center; }
  .vob-vhead-cell.align-left   { text-align: left; }
  .vob-vrows {
    flex: 1 1 0; min-height: 0;
    overflow-y: auto; overflow-x: hidden;
    display: flex; flex-direction: column; gap: 6px;
    padding: 8px var(--vob-px, 12px);
  }
  .vob-vempty {
    color: #71717a; font-style: italic; font-size: 13px;
    padding: 24px 8px; text-align: center;
  }
  .vob-vrow {
    display: grid; grid-template-columns: var(--vob-grid);
    align-items: center; column-gap: 12px;
    flex: 0 0 auto; min-height: 52px;
    padding: 9px var(--vob-px, 12px); border-radius: 12px;
    background: rgba(255,255,255,.022); border: 1px solid rgba(255,255,255,.055);
    cursor: pointer;
    transition: border-color .14s, background .14s, box-shadow .14s, transform .14s;
  }
  .vob-vrow:hover {
    background: rgba(167,139,250,.06);
    border-color: rgba(167,139,250,.3);
    box-shadow: 0 6px 22px -10px rgba(0,0,0,.7),
                0 0 0 1px rgba(167,139,250,.12);
  }
  .vob-vrow--active {
    border-color: rgba(167,139,250,.55) !important;
    background: rgba(167,139,250,.10) !important;
    box-shadow: 0 0 0 1px rgba(167,139,250,.30), 0 6px 20px -10px rgba(167,139,250,.45) !important;
  }
  .vob-chk {
    appearance: none; -webkit-appearance: none;
    width: 15px; height: 15px;
    border: 1.5px solid #52525b; border-radius: 4px;
    background: transparent; cursor: pointer;
    transition: border-color .12s, background .12s;
    display: block; align-self: center;
  }
  .vob-chk:checked {
    background: #a78bfa; border-color: #a78bfa;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 10 8' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 4l3 3 5-6' stroke='white' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: center; background-size: 10px 8px;
  }
  .vob-chk:hover:not(:checked) { border-color: #a78bfa; }
  .vob-vc-center { display: flex; align-items: center; justify-content: center; min-width: 0; }
  .vob-vrow-company { font-size: 12px; color: #a1a1aa; font-weight: 400; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .vob-vrow-title   { font-size: 13px; font-weight: 600; color: #fafafa; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .vob-vrow-salary  { font-size: 12px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

  /* Универсальный бейдж (match/статус) — цвет приходит инлайн */
  .vob-badge {
    flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    padding: 3px 9px; border-radius: 7px;
    font-size: 11px; font-weight: 700; line-height: 1; white-space: nowrap;
  }

  /* Футер пагинации */
  .vob-pager {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; border-top: 1px solid #26262f;
    flex: 0 0 auto;
  }
  .vob-pager-info { font-size: 12px; color: #8b8b96; }
  .vob-pager-page { font-size: 12px; color: #a1a1aa; min-width: 56px; text-align: center; }
  .vob-pager-size {
    cursor: pointer; font-size: 12px; font-weight: 600;
    padding: 3px 9px; border-radius: 7px; color: #8b8b96;
    border: 1px solid #2a2a36; transition: all .12s;
  }
  .vob-pager-size:hover { color: #c4b5fd; border-color: #34344a; }
  .vob-pager-size.active {
    color: #a78bfa; background: rgba(167,139,250,.12);
    border-color: rgba(167,139,250,.4);
  }
  .vob-pager-nav {
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    width: 28px; height: 28px; border-radius: 7px;
    color: #a1a1aa; border: 1px solid #2a2a36; transition: all .12s;
  }
  .vob-pager-nav:hover { color: #a78bfa; border-color: rgba(167,139,250,.4); }
  .vob-pager-nav.disabled { opacity: .35; cursor: default; pointer-events: none; }

  /* Заголовки секций правой панели деталей */
  /* Заголовок секции drawer — выраженный блок с акцентной палочкой. */
  .vob-detail-section {
    position: relative;
    font-size: 12px; font-weight: 700; letter-spacing: .06em;
    text-transform: uppercase; color: #e4e4e7;
    margin-top: 18px; padding: 6px 10px 6px 14px;
    border-radius: 8px;
    background: linear-gradient(90deg, rgba(167,139,250,.08), transparent 70%);
  }
  .vob-detail-section::before {
    content: ""; position: absolute; left: 0; top: 4px; bottom: 4px;
    width: 4px; border-radius: 99px;
    background: linear-gradient(180deg, #fb7a3c, #a78bfa);
  }
  .vob-detail-section:first-child { margin-top: 4px; }

  /* ── Layout-хелперы ───────────────────────────────────── */
  .vob-muted  { color: #71717a !important; }
  /* padding-right: контент отступает от скролл-жёлоба, скролл не липнет
     к процентам/тексту. scrollbar-gutter резервирует место под скролл,
     чтобы при его появлении контент не дёргался. */
  .vob-scroll {
    overflow-y: auto; overflow-x: hidden; min-height: 0;
    padding-right: 8px; scrollbar-gutter: stable;
  }
  .q-splitter__panel { overflow: hidden; }

  /* ── CRM layout ────────────────────────────────────────── */
  .vob-crm-root {
    display: flex; flex-direction: column; gap: 10px;
    width: 100%; height: 100%; min-height: 0; overflow: hidden;
    padding: 0;
  }

  /* KPI-строка */
  .vob-crm-kpi-row {
    display: flex; flex-wrap: nowrap; gap: 8px; flex: 0 0 auto;
  }

  /* ── Панель поиска / фильтров ─────────────────────────────── */
  .vob-search-panel {
    flex: 0 0 auto;
    background: rgba(20,20,25,.66); backdrop-filter: blur(16px) saturate(1.1);
    -webkit-backdrop-filter: blur(16px) saturate(1.1);
    border: 1px solid rgba(255,255,255,.07); border-radius: 14px;
    padding: 0; display: flex; flex-direction: column; overflow: hidden;
  }

  /* Строка 1: поле поиска */
  .vob-search-row {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 14px;
    border-bottom: 1px solid #26262f;
  }
  .vob-search-field-wrap {
    flex: 1 1 0; min-width: 0;
    display: flex; align-items: center; gap: 8px;
    background: #0f0f14; border: 1px solid #2a2a36; border-radius: 10px;
    padding: 0 12px; height: 40px;
    transition: border-color .15s;
  }
  .vob-search-field-wrap:focus-within {
    border-color: rgba(167,139,250,.6);
    box-shadow: 0 0 0 3px rgba(167,139,250,.08);
  }
  .vob-search-icon {
    font-size: 18px; color: #52525b; flex: 0 0 auto;
  }
  .vob-search-input {
    flex: 1 1 0; min-width: 0;
  }
  /* Убираем все рамки у borderless select внутри нашей обёртки */
  .vob-search-input .q-field__control,
  .vob-search-input .q-field__control::before,
  .vob-search-input .q-field__control::after {
    background: transparent !important;
    border: none !important; box-shadow: none !important;
    min-height: 40px !important; height: 40px !important;
  }
  .vob-search-input .q-field__native,
  .vob-search-input .q-field__input {
    color: #fafafa !important; font-size: 14px !important;
    padding: 0 !important; min-height: 40px !important;
  }
  .vob-search-input .q-field__label { color: #52525b !important; font-size: 14px !important; top: 10px !important; }
  .vob-search-btn {
    flex: 0 0 auto; height: 40px !important;
    border-radius: 10px !important; font-size: 13px !important;
    padding: 0 16px !important;
  }
  .vob-search-divider {
    width: 1px; height: 22px; background: #2a2a36; flex: 0 0 auto;
  }

  /* Строка 2: чипы-фильтры */
  .vob-filters-row {
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    padding: 10px 14px 12px;
  }

  /* Статус-строка поиска: компактная полоса внизу панели, не растягивает её */
  .vob-search-statusbar {
    display: flex; align-items: center; gap: 10px;
    padding: 0 14px 8px;
  }
  .vob-search-statusbar .vob-search-progress {
    flex: 1 1 auto; min-width: 0; height: 4px; border-radius: 2px;
    margin: 0;
  }

  /* Обёртка чипа — ФИКСИРОВАННАЯ ширина: текст значения обрезается
     по ellipsis, чип не меняет размер → соседи справа не двигаются. */
  .vob-chip-wrap {
    position: relative;
    flex: 0 0 132px;
    width: 132px;
    min-width: 132px;
    max-width: 132px;
  }

  /* Кнопка-чип — стеклянная пилюля в тон полю поиска */
  .vob-chip-btn {
    display: flex !important; align-items: center !important; gap: 6px !important;
    height: 36px !important; padding: 0 14px !important;
    width: 100% !important;
    background: rgba(255,255,255,.03) !important;
    border: 1px solid rgba(255,255,255,.08) !important;
    border-radius: 10px !important;
    transition: border-color .14s, background .14s, box-shadow .14s !important;
  }
  .vob-chip-btn:hover {
    background: rgba(167,139,250,.07) !important;
    border-color: rgba(167,139,250,.3) !important;
  }
  /* Активный чип (выбрано значение) — фирменная подсветка */
  .vob-chip-btn.vob-chip-active {
    background: rgba(167,139,250,.12) !important;
    border-color: rgba(167,139,250,.4) !important;
    box-shadow: 0 0 0 1px rgba(167,139,250,.15) !important;
  }
  /* Quasar-обёртки внутри кнопки — растягиваем чтобы текст обрезался */
  .vob-chip-btn .q-btn__wrapper,
  .vob-chip-btn .q-btn__content {
    width: 100% !important; min-width: 0 !important;
    display: flex !important; align-items: center !important; gap: 4px !important;
    flex-wrap: nowrap !important;
  }
  .vob-chip-text {
    flex: 1 1 0; min-width: 0;
    font-size: 12px !important; font-weight: 500 !important;
    color: #a1a1aa !important; line-height: 1 !important;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  /* Кружок-счётчик выбранных значений в чипе */
  .vob-chip-count {
    flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 18px; height: 18px; padding: 0 5px;
    border-radius: 99px;
    background: #a78bfa; color: #1a1a22 !important;
    font-size: 11px !important; font-weight: 700 !important;
    line-height: 1 !important;
  }
  .vob-chip-text--active {
    color: #c4b5fd !important;
  }
  .vob-chip-arrow {
    flex: 0 0 auto;
    font-size: 14px !important; color: #52525b !important;
    line-height: 1 !important;
  }

  /* Выпадающее меню чипа */
  .vob-chip-menu {
    background: #18181b !important;
    border: 1px solid #2a2a36 !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 32px rgba(0,0,0,.7) !important;
    padding: 4px !important;
    min-width: 160px;
  }
  .vob-chip-item {
    display: block;
    padding: 7px 12px; border-radius: 6px;
    font-size: 13px; color: #a1a1aa;
    cursor: pointer; transition: background .1s, color .1s;
    user-select: none;
  }
  .vob-chip-item:hover { background: rgba(255,255,255,.05); color: #fafafa; }
  .vob-chip-item--active { color: #a78bfa !important; background: rgba(167,139,250,.10) !important; }

  /* Поля ввода во второй строке (з/п и поиск) */
  .vob-filter-salary-input,
  .vob-filter-search-input { flex: 0 0 auto; }
  .vob-filter-salary-input { width: 108px !important; }
  .vob-filter-search-input { flex: 1 1 160px !important; min-width: 140px !important; }
  .vob-filter-salary-input .q-field__control,
  .vob-filter-search-input .q-field__control {
    height: 36px !important; min-height: 36px !important;
    border-radius: 10px !important;
  }
  .vob-filter-salary-input .q-field__label,
  .vob-filter-search-input .q-field__label { font-size: 11px !important; top: 7px !important; }
  .vob-filter-salary-input .q-field__native,
  .vob-filter-search-input .q-field__native { font-size: 12px !important; padding-top: 4px !important; min-height: 32px !important; }

  /* Совместимость со старым кодом */
  .vob-filter-divider {
    width: 1px; height: 20px; background: #3f3f46; flex: 0 0 auto;
  }
  .vob-auth-badge {
    font-size: 11px; font-weight: 600; letter-spacing: .02em;
    padding: 3px 8px; border-radius: 6px; cursor: default; white-space: nowrap;
    color: #71717a; background: #27272a; border: 1px solid #3f3f46;
  }
  .vob-btn-link { font-size: 12px !important; color: #a78bfa !important; }
  .vob-btn-icon { color: #52525b !important; }

  /* Bulk-панель */
  .vob-bulk-bar {
    flex: 0 0 auto;
    background: rgba(167,139,250,.08);
    border: 1px solid rgba(167,139,250,.35);
    border-radius: 10px; padding: 7px 14px;
  }
  .vob-bulk-inner {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  }
  .vob-bulk-count { font-size: 13px; font-weight: 600; color: #c4b5fd; }
  .vob-bulk-div { width: 1px; height: 20px; background: rgba(167,139,250,.3); flex: 0 0 auto; }
  .vob-bulk-select { min-width: 160px !important; }

  /* Тело CRM: таблица + drawer */
  .vob-crm-body {
    flex: 1 1 0; min-height: 0; position: relative;
    display: flex; overflow: hidden;
  }

  /* Карточка таблицы */
  .vob-table-card {
    flex: 1 1 0; min-width: 0; min-height: 0; overflow: hidden;
    background: rgba(20,20,25,.66); backdrop-filter: blur(16px) saturate(1.1);
    -webkit-backdrop-filter: blur(16px) saturate(1.1);
    border: 1px solid rgba(255,255,255,.07); border-radius: 12px;
    display: flex; flex-direction: column;
  }
  .vob-table-header {
    display: flex; align-items: center; gap: 8px;
    padding: 10px 14px 8px; border-bottom: 1px solid #26262f; flex: 0 0 auto;
  }
  .vob-table-title {
    font-size: 13px; font-weight: 600; color: #e4e4e7;
  }
  .vob-table-header-spacer { flex: 1 1 0; }
  .vob-table-count {
    font-size: 11px; font-weight: 600; color: #71717a;
    background: #27272a; border: 1px solid #3f3f46;
    padding: 2px 8px; border-radius: 6px;
  }

  /* Drawer деталей вакансии — стеклянный, в тон карточкам */
  .vob-drawer {
    position: absolute; top: 0; right: 0; bottom: 0;
    width: 420px;
    background: rgba(16,16,21,.86);
    backdrop-filter: blur(20px) saturate(1.1);
    -webkit-backdrop-filter: blur(20px) saturate(1.1);
    border-left: 1px solid rgba(255,255,255,.08);
    box-shadow: -12px 0 48px rgba(0,0,0,.55);
    display: flex; flex-direction: column;
    z-index: 10; overflow: hidden;
    animation: vob-drawer-in .22s cubic-bezier(.4,0,.2,1);
  }
  @keyframes vob-drawer-in {
    from { transform: translateX(100%); opacity: 0; }
    to   { transform: translateX(0);    opacity: 1; }
  }
  .vob-drawer-head {
    display: flex; align-items: flex-start; gap: 10px;
    padding: 14px 16px 10px; border-bottom: 1px solid #26262f; flex: 0 0 auto;
  }
  .vob-drawer-titles { flex: 1 1 0; min-width: 0; }
  .vob-drawer-title  { font-size: 15px; font-weight: 700; color: #fafafa; line-height: 1.3; }
  .vob-drawer-meta   { font-size: 12px; margin-top: 2px; }
  .vob-drawer-close-btn {
    flex: 0 0 auto; width: 28px; height: 28px; border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    cursor: pointer; transition: background .12s;
  }
  .vob-drawer-close-btn:hover { background: rgba(255,255,255,.07); }
  .vob-drawer-actions {
    padding: 10px 16px; border-bottom: 1px solid #26262f; flex: 0 0 auto;
    display: flex; flex-direction: column; gap: 8px;
  }
  .vob-drawer-status { width: 100% !important; }
  /* Кнопки drawer — ровная сетка, единая высота, ничего не «прыгает». */
  .vob-drawer-btns {
    display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
  }
  .vob-drawer-btns .q-btn {
    height: 38px !important; border-radius: 9px !important;
    min-height: 38px !important; width: 100% !important;
    padding: 0 12px !important;
  }
  /* Центрируем содержимое (иконка+текст) — иначе разъезжается. */
  .vob-drawer-btns .q-btn .q-btn__content,
  .vob-drawer-btns .q-btn .q-btn__wrapper {
    padding: 0 !important; height: 100% !important; min-height: 38px !important;
    display: flex !important; align-items: center !important;
    justify-content: center !important; flex-wrap: nowrap !important;
  }
  /* Кнопка удаления — как все: на всю ячейку сетки, иконка по центру. */
  .vob-drawer-btns .vob-drawer-del .q-icon { font-size: 18px !important; }
  .vob-drawer-body { flex: 1 1 0; min-height: 0; overflow: hidden; display: flex; flex-direction: column; padding: 0 16px 12px; }

  /* Multi-select фильтры: явная подсветка выбранных строк в выпадающем списке. */
  .vob-opt-selected {
    color: #a78bfa !important;
    font-weight: 600 !important;
    background: rgba(167,139,250,0.12) !important;
  }
  /* Чипсы выбранных значений в поле фильтра (use-chips) — в тон акценту. */
  .q-select .q-chip {
    background: rgba(167,139,250,0.16) !important;
    color: #c4b5fd !important;
    border: 1px solid rgba(167,139,250,0.40);
    font-weight: 500;
  }

  /* Чип «alpha» — обычный inline-элемент сразу справа от названия.
     Не трогаем раскладку иконки/текста, только небольшой отступ слева. */
  .vob-alpha-chip {
    margin-left: 8px; flex: 0 0 auto;
    font-size: 8px; font-weight: 700; letter-spacing: .04em;
    text-transform: uppercase; line-height: 1;
    padding: 2px 5px; border-radius: 4px;
    color: #c4b5fd; background: rgba(167,139,250,.14);
    border: 1px solid rgba(167,139,250,.35);
  }

  /* ── Сайдбар ──────────────────────────────────────────── */
  /* Марка-логотип — квадрат с фирменным градиентом */
  .vob-logo-mark {
    width: 30px; height: 30px; border-radius: 9px; flex: 0 0 auto;
    display: flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, #fb7a3c, #a78bfa);
    box-shadow: 0 2px 10px -3px rgba(167,139,250,.5);
  }
  .vob-logo-mark .material-icons { color: #fff; font-size: 18px; }

  /* Гамбургер сайдбара — тихая иконка, плашка появляется на hover. */
  .q-btn.vob-rail-burger {
    width: 32px !important; height: 32px !important;
    min-height: 32px !important; border-radius: 8px !important;
    color: #71717a !important;
    background: transparent !important;
    border: none !important; box-shadow: none !important;
    transition: background .14s, color .14s !important;
  }
  .q-btn.vob-rail-burger:hover {
    background: rgba(167,139,250,.1) !important;
    color: #c4b5fd !important;
  }
  .q-btn.vob-rail-burger .q-icon { font-size: 19px !important; }
  /* Гасим Quasar ripple/overlay, чтобы не было кружка-вспышки. */
  .q-btn.vob-rail-burger .q-focus-helper { display: none !important; }

  .vob-rail.vob-collapsed { width: 60px !important; min-width: 60px !important; }
  .vob-rail.vob-collapsed .vob-rail-hide  { display: none !important; }
  .vob-rail.vob-collapsed .q-tab__label   { display: none !important; }
  .vob-rail.vob-collapsed .q-tab          { justify-content: center !important; }

  /* Заголовок секции в сайдбаре */
  .vob-rail-section {
    font-size: 10px; font-weight: 700; letter-spacing: .08em;
    text-transform: uppercase; color: #3f3f46;
    padding: 12px 16px 4px;
    line-height: 1;
  }

  /* Вкладки сайдбара */
  .q-tab {
    position: relative;
    border-radius: 9px !important;
    margin: 2px 8px !important;
    padding: 0 12px !important;
    min-height: 40px !important;
    justify-content: flex-start !important;
    transition: background .14s, color .14s !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #a1a1aa !important;
  }
  .q-tab:hover:not(.q-tab--active) {
    background: rgba(255,255,255,0.04) !important;
    color: #fafafa !important;
  }
  /* Активный пункт — выраженная плашка + акцентная палочка слева (референс) */
  .q-tab--active {
    background: rgba(167, 139, 250, 0.14) !important;
    color: #ddd6fe !important;
    box-shadow: inset 0 0 0 1px rgba(167,139,250,.18) !important;
  }
  .q-tab--active::before {
    content: ""; position: absolute; left: 0; top: 9px; bottom: 9px;
    width: 3px; border-radius: 99px;
    background: linear-gradient(180deg, #fb7a3c, #a78bfa);
  }
  .q-tab--active .q-icon { color: #c4b5fd !important; }
  .q-tab__indicator { display: none !important; }

  /* ── Tab-panels контент ───────────────────────────────── */
  /* Прозрачные — чтобы фоновое свечение (body::before) просвечивало насквозь */
  .q-tab-panel  { background: transparent !important; }
  .q-tab-panels { background: transparent !important; }
  .q-layout, .q-page-container, .q-page { background: transparent !important; }

  /* ── Лампочка авторизации в CRM-баре ─────────────────── */
  .vob-auth-dot {
    font-size: 14px; cursor: default;
    color: #71717a; line-height: 1;
    flex: 0 0 auto;
  }

  /* ── Вкладка Настройки ────────────────────────────────── */
  .vob-settings-root {
    display: flex; flex-direction: column;
    width: 100%; height: 100%;
  }
  .vob-settings-scroll {
    flex: 1 1 0;
    max-height: calc(100vh - 80px);
    overflow-y: auto; overflow-x: hidden;
    display: flex; flex-direction: column; gap: 16px;
    padding: 4px 8px 32px 0;
    scrollbar-gutter: stable;
    width: 100%;
  }
  .vob-settings-section {
    background: rgba(20,20,25,.66); backdrop-filter: blur(16px) saturate(1.1);
    -webkit-backdrop-filter: blur(16px) saturate(1.1);
    border: 1px solid rgba(255,255,255,.07); border-radius: 14px;
    flex: 0 0 auto;
    display: flex; flex-direction: column;
    width: 100%;
  }
  .vob-settings-section-head {
    display: flex; align-items: center; gap: 8px;
    padding: 12px 18px; border-bottom: 1px solid #26262f;
    background: rgba(167,139,250,.04);
    border-radius: 14px 14px 0 0;
    flex: 0 0 auto;
  }
  .vob-settings-section-title {
    font-size: 13px; font-weight: 700; color: #e4e4e7; letter-spacing: .01em;
  }
  .vob-settings-body {
    display: flex; flex-direction: column;
    border-radius: 0 0 14px 14px;
    overflow: hidden;
  }
  .vob-settings-row {
    display: flex; align-items: center; gap: 16px;
    padding: 14px 18px;
    border-bottom: 1px solid #1f1f27;
    transition: background .1s;
  }
  .vob-settings-row:last-child { border-bottom: none; }
  .vob-settings-row:hover { background: rgba(255,255,255,.02); }
  .vob-settings-label-group {
    flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; gap: 2px;
  }
  .vob-settings-label {
    font-size: 13px; font-weight: 500; color: #e4e4e7;
  }
  .vob-settings-hint {
    font-size: 12px; color: #71717a; line-height: 1.4;
  }
  /* Зона контролов — фиксированная ширина, выравнивание по правому краю */
  .vob-settings-control {
    flex: 0 0 240px; width: 240px;
    display: flex; align-items: center; justify-content: flex-end; gap: 8px;
  }
  /* Кнопки-действия — ЖЁСТКО одинаковый размер (не min-width, а фикс). */
  .vob-settings-action-btn {
    width: 200px !important; min-width: 200px !important; max-width: 200px !important;
    height: 38px !important; min-height: 38px !important;
    border-radius: 9px !important;
    padding: 0 14px !important;
  }
  /* Центрируем содержимое — иначе иконка+текст разъезжаются (accent vs outline). */
  .vob-settings-action-btn .q-btn__content {
    padding: 0 !important; height: 100% !important; width: 100% !important;
    display: flex !important; align-items: center !important;
    justify-content: center !important; flex-wrap: nowrap !important; gap: 6px;
  }
  .vob-settings-action-btn .q-btn__wrapper {
    min-height: 38px !important; padding: 0 !important; width: 100% !important;
    display: flex !important; align-items: center !important;
    justify-content: center !important;
  }

  /* Заголовок раздела учебника — крупнее и жирнее вложенных тем,
     чтобы раздел доминировал, а не был мельче своих же пунктов. */
  .vob-hb-section > .q-item .q-item__label,
  .vob-hb-section > .q-expansion-item__container > .q-item .q-item__label {
    font-size: 14px !important; font-weight: 700 !important;
    color: #e4e4e7 !important;
  }

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
  /* Primary / CTA — спокойная фиолетовая заливка. Яркий оранж→фиолет
     градиент на больших кнопках выжигал; здесь приглушённый фиолет с
     еле заметным тёплым оттенком слева, без кричащего свечения. */
  .q-btn.bg-primary {
    background: linear-gradient(135deg, #8b6fd6 0%, #7c5fcf 100%) !important;
    color: #fff !important;
    box-shadow: 0 2px 10px -4px rgba(124,95,207,.4) !important;
  }
  .q-btn.bg-primary:hover {
    background: linear-gradient(135deg, #9a7fe0 0%, #8a6dd9 100%) !important;
    box-shadow: 0 4px 16px -5px rgba(124,95,207,.5) !important;
  }
  /* Outline-кнопки — нейтральная база (НЕ синий Quasar-primary).
     :not(.text-negative) — сохраняем красные кнопки удаления семантичными. */
  .q-btn--outline:not(.text-negative) {
    border-color: #3a3a44 !important;
    color: #c4c4cc !important;
    background: rgba(255,255,255,.02) !important;
  }
  .q-btn--outline:not(.text-negative) .q-icon { color: #c4c4cc !important; }
  .q-btn--outline:not(.text-negative):hover {
    border-color: #a78bfa !important;
    color: #c4b5fd !important;
    background: rgba(167,139,250,.08) !important;
  }
  .q-btn--outline:not(.text-negative):hover .q-icon { color: #c4b5fd !important; }
  /* Outline-кнопки крупнее по «телу», шрифт не меняем (font-size прежний). */
  .q-btn--outline .q-btn__content {
    padding: 5px 6px !important;
  }
  .q-btn--outline.q-btn--dense .q-btn__content {
    min-height: 34px;
  }
  .q-btn--flat:hover { background: rgba(255,255,255,0.05) !important; }

  /* Универсальный «выравниватель» — кнопки одной высоты и посадки в ряд,
     независимо от типа (accent/outline). Гасит разный дефолтный padding. */
  .q-btn.vob-eq-btn {
    height: 38px !important; min-height: 38px !important;
    border-radius: 9px !important; padding: 0 14px !important;
  }
  .q-btn.vob-eq-btn .q-btn__content {
    padding: 0 !important; height: 100% !important;
    display: flex !important; align-items: center !important;
    justify-content: center !important; flex-wrap: nowrap !important; gap: 6px;
  }
  .q-btn.vob-eq-btn .q-btn__wrapper {
    min-height: 38px !important; padding: 0 !important;
    display: flex !important; align-items: center !important;
  }

  /* Кнопка «Обновить» в хедерах секций — фирменная пилюля.
     flat-база, чтобы Quasar не красил рамку/текст в синий primary;
     цвет задаём целиком сами. */
  .q-btn.vob-btn-refresh {
    background: rgba(167,139,250,.10) !important;
    border: 1px solid rgba(167,139,250,.28) !important;
    color: #c4b5fd !important;
    border-radius: 8px !important;
    padding: 0 12px !important;
    min-height: 34px !important;
  }
  .q-btn.vob-btn-refresh .q-icon,
  .q-btn.vob-btn-refresh .q-btn__content { color: #c4b5fd !important; }
  .q-btn.vob-btn-refresh:hover {
    background: rgba(167,139,250,.18) !important;
    border-color: rgba(167,139,250,.5) !important;
    color: #ddd6fe !important;
  }
  .q-btn.vob-btn-refresh:hover .q-icon { color: #ddd6fe !important; }
  /* Высокий вариант — для строки поиска (рядом с 40px-кнопкой «Найти»). */
  .q-btn.vob-btn-refresh--tall {
    height: 40px !important; border-radius: 10px !important;
  }

  /* Главное действие (CTA) — фиолетовый акцент (единый акцент приложения).
     ВАЖНО: текст фиолетовый (#c4b5fd), НЕ белый — белый на фиолетовом фоне
     пересвечивал и резал глаз. Стеклянная заливка, не плоский яркий фон. */
  .q-btn.vob-btn-accent {
    background: rgba(167,139,250,.16) !important;
    border: 1px solid rgba(167,139,250,.45) !important;
    color: #c4b5fd !important;
    box-shadow: 0 0 0 1px rgba(167,139,250,.08) !important;
  }
  .q-btn.vob-btn-accent .q-icon { color: #c4b5fd !important; }
  .q-btn.vob-btn-accent:hover {
    background: rgba(167,139,250,.24) !important;
    border-color: rgba(167,139,250,.62) !important;
    color: #ddd6fe !important;
    box-shadow: 0 4px 16px -6px rgba(167,139,250,.35) !important;
  }
  .q-btn.vob-btn-accent:hover .q-icon { color: #ddd6fe !important; }

  /* Тулбар действий (Письма, Интервью) — единая высота И внутренняя посадка,
     чтобы accent и outline стояли ровно (у них разный дефолтный padding). */
  .vob-action-bar .vob-act-btn {
    height: 38px !important; min-height: 38px !important;
    border-radius: 9px !important;
    padding: 0 14px !important;
  }
  .vob-action-bar .vob-act-btn .q-btn__content {
    padding: 0 !important;
    height: 100% !important;
    display: flex !important; align-items: center !important;
    flex-wrap: nowrap !important;
  }
  .vob-action-bar .q-field__control {
    height: 38px !important; min-height: 38px !important;
    border-radius: 9px !important;
  }
  .vob-action-bar .vob-act-btn .q-btn__wrapper {
    min-height: 38px !important; padding: 0 !important;
    display: flex !important; align-items: center !important;
  }

  /* Переключатель режимов учебника */
  .q-btn-toggle .q-btn__content { white-space: nowrap; }
  .q-btn-toggle .q-btn {
    background: transparent !important;
    border-color: #3f3f46 !important;
    color: #71717a !important;
  }
  .q-btn-toggle .q-btn.q-btn--active,
  .q-btn-toggle .q-btn[aria-pressed="true"],
  .vob-hb-toggle .q-btn.q-btn--active,
  .vob-hb-toggle .q-btn[aria-pressed="true"] {
    background: rgba(167,139,250,.14) !important;
    color: #c4b5fd !important;
    border-color: rgba(167,139,250,.35) !important;
  }
  /* Глушим возможную сплошную заливку от Quasar toggle-color */
  .vob-hb-toggle .q-btn--active .q-btn__content,
  .vob-hb-toggle .q-btn[aria-pressed="true"] .q-btn__content {
    color: #c4b5fd !important;
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
  /* Плейсхолдер — приглушённо-серый, чтобы не путался с введённым текстом. */
  .q-field__native::placeholder,
  .q-field__input::placeholder { color: #52525b !important; opacity: 1 !important; }
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

  /* ── Описание вакансии (raw HTML из hh.ru) ───────────── */
  .vob-vacancy-desc { line-height: 1.6; color: #d4d4d8; }
  .vob-vacancy-desc p { margin: .45em 0; }
  .vob-vacancy-desc ul,
  .vob-vacancy-desc ol { margin: .4em 0; padding-left: 1.4em; }
  .vob-vacancy-desc li { margin: .18em 0; }
  .vob-vacancy-desc strong,
  .vob-vacancy-desc b { color: #fafafa; font-weight: 600; }
  .vob-vacancy-desc em,
  .vob-vacancy-desc i { color: #a1a1aa; }
  .vob-vacancy-desc a { color: #a78bfa; text-decoration: underline; text-underline-offset: 2px; }
  .vob-vacancy-desc h1,.vob-vacancy-desc h2,.vob-vacancy-desc h3 {
    color: #fafafa; font-weight: 600; margin: .6em 0 .25em;
  }
  .vob-vacancy-desc h1 { font-size: 1.1rem; }
  .vob-vacancy-desc h2 { font-size: 1rem; }
  .vob-vacancy-desc h3 { font-size: .95rem; }
  /* Заголовки секций вакансии: «Обязанности:», «Требования:» и т.п. */
  .vob-vacancy-desc .vob-sec-header {
    color: #e4e4e7; font-weight: 600; margin: .8em 0 .15em;
    font-size: .88rem; text-transform: uppercase;
    letter-spacing: .04em; opacity: .7;
  }
  /* Убираем отступ первого и лишние пустые блоки */
  .vob-vacancy-desc > p:first-child { margin-top: 0; }
  .vob-vacancy-desc br + br { display: none; }

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
  /* Quasar переопределяет color внутри badge — форсируем белый как базовый.
     Динамические бейджи задают background через inline-style; color:#fff
     гарантирует читаемость на любом полупрозрачном фоне. */
  .q-badge { color: #fff !important; }

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
