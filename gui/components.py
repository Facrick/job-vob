import flet as ft

# ── Палитра ───────────────────────────────────────────────────
ACCENT = ft.Colors.INDIGO_300
CARD_BG = ft.Colors.SURFACE_CONTAINER_HIGH
CARD_RADIUS = 14
GAP = 12
# Ниже этой ширины окна двухпанельные вкладки складываются вертикально.
BREAKPOINT = 860


# ── Переиспользуемые компоненты ──────────────────────────────
def primary_btn(
    text, on_click, icon=None, bgcolor=None, color=None, expand=False, width=None
):
    return ft.FilledButton(
        content=text,
        on_click=on_click,
        icon=icon,
        bgcolor=bgcolor,
        color=color,
        expand=expand,
        width=width,
        height=42,
    )


def secondary_btn(text, on_click, icon=None, expand=False):
    return ft.OutlinedButton(
        content=text, on_click=on_click, icon=icon, expand=expand, height=42
    )


def card(content, *, expand=False, padding=16):
    return ft.Container(
        content=content,
        bgcolor=CARD_BG,
        border_radius=CARD_RADIUS,
        padding=padding,
        expand=expand,
    )


def page_column(controls, **kw):
    """Корневой Column вкладки: тянет карточки на всю ширину (STRETCH)."""
    return ft.Column(
        expand=True,
        spacing=GAP,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        controls=controls,
        **kw,
    )


def section_title(text, icon=None):
    row = []
    if icon:
        row.append(ft.Icon(icon, size=18, color=ACCENT))
    row.append(ft.Text(text, size=15, weight=ft.FontWeight.W_600))
    return ft.Row(row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)
