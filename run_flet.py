import flet as ft
import os
from dotenv import load_dotenv
from gui.controllers import MainController
from gui.flet_views import MainView

def main(page: ft.Page):
    # Явно указываем путь к .env файлу
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
    load_dotenv(dotenv_path=dotenv_path)

    # Настройки страницы
    page.title = "QA Smart Assistant Pro | Job CRM"
    page.vertical_alignment = ft.MainAxisAlignment.START
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    
    # Инициализация контроллера и представления
    controller = MainController()
    main_view = MainView(controller)
    
    # Привязка представления и страницы к контроллеру
    controller.bind_flet_view(main_view, page)
    
    # Добавляем главное представление на страницу
    page.add(main_view)
    
    # Обновляем страницу, чтобы показать начальный UI
    page.update()

if __name__ == "__main__":
    ft.app(target=main)
