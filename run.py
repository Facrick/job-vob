import flet as ft
from gui.flet_views import FletMainWindow
from gui.controllers import MainController

def main(page: ft.Page):
    """Точка входа для Flet-приложения."""
    controller = MainController()
    view = FletMainWindow(controller)
    view.setup_page(page)
    controller.bind_flet_view(view)

if __name__ == "__main__":
    ft.app(target=main)