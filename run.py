import os

import flet as ft
from dotenv import load_dotenv

from gui.controllers import MainController
from gui.flet_views import MainView


def main(page: ft.Page):
    # Явно указываем путь к .env файлу
    dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path=dotenv_path)

    # Настройки страницы
    page.title = "QA Smart Assistant Pro | Job CRM"
    page.padding = 0
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.window.min_width = 380
    page.window.min_height = 560

    # Инициализация контроллера и представления
    controller = MainController()
    main_view = MainView(controller)

    # Добавляем контент на страницу (setup_page сам вызывает page.add)
    main_view.setup_page(page)

    # Привязка представления и страницы к контроллеру (загружает данные)
    controller.bind_flet_view(main_view, page)


if __name__ == "__main__":
    ft.run(main)
