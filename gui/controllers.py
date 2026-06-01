import os
import re
import logging
import json
import webbrowser
import shutil
import threading
import flet as ft
from matplotlib.figure import Figure

from core.database import VacancyRepository, DataExporter
from core.ai_engine import ResumeEntity, LetterAnalyzer
from core.handbook import QAHandbook
from core.parser import HHParser

class FletLogHandler(logging.Handler):
    def __init__(self, logs_text_widget, page):
        super().__init__()
        self.logs_text = logs_text_widget
        self.page = page

    def emit(self, record):
        msg = self.format(record)
        self.logs_text.value += msg + "\n"
        self.page.update()

class MainController:
    def __init__(self):
        self.repo = VacancyRepository()
        self.analyzer = LetterAnalyzer()
        self.exporter = DataExporter(self.repo)
        self.resume = ResumeEntity()
        self.handbook = QAHandbook()
        self.view = None
        self.page = None
        self.selected_vacancy_id = None
        self.mock_chat_history = []

    def bind_flet_view(self, view, page):
        self.view = view
        self.page = page
        self.setup_logging_bridge()
        self.refresh_table_data()
        self.load_handbook()

    def setup_logging_bridge(self):
        logs_text = self.view.logs_tab.logs_text
        handler = FletLogHandler(logs_text, self.page)
        handler.setFormatter(logging.Formatter('%(asctime)s - [%(levelname)s] - %(message)s', '%H:%M:%S'))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

    def load_handbook(self):
        sections = self.handbook.get_all_sections()
        tree = self.view.handbook_tab.tree_handbook
        for section_name, questions in sections.items():
            tree.controls.append(ft.Text(section_name, weight=ft.FontWeight.BOLD, size=16))
            for q in questions:
                tree.controls.append(
                    ft.Text(
                        q["question"], 
                        data=q["answer"], 
                        on_click=self.handle_handbook_click
                    )
                )
        self.page.update()

    def handle_handbook_click(self, e):
        self.view.handbook_tab.text_handbook.value = e.control.data
        self.page.update()

    def refresh_table_data(self):
        if not self.view or not self.page:
            return
            
        status_filter = self.view.scout_tab.combo_status_filter.value
        vacancies = self.repo.get_vacancies_filtered(status_filter)
        
        table = self.view.scout_tab.data_table
        table.rows.clear()

        for v in vacancies:
            table.rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(v['company'])),
                        ft.DataCell(ft.Text(v['title'])),
                        ft.DataCell(ft.Text(v['id'])),
                        ft.DataCell(ft.Text(v['status'])),
                        ft.DataCell(ft.Text("Open", color="blue", data=f"https://hh.ru/vacancy/{v['id']}", on_click=self.open_url)),
                    ],
                    data=v['id'],
                    on_select_changed=self.handle_table_click
                )
            )
        self.page.update()

    def open_url(self, e):
        self.page.launch_url(e.control.data)

    def handle_table_click(self, e):
        self.selected_vacancy_id = e.control.data
        
        existing_letter = self.repo.get_cover_letter(self.selected_vacancy_id)
        if existing_letter:
            self.view.letters_tab.text_letter.value = existing_letter['letter_text']
            self.view.letters_tab.text_recs.value = existing_letter['recommendations']
        else:
            self.view.letters_tab.text_letter.value = ""
            self.view.letters_tab.text_recs.value = ""

        saved_chat = self.repo.get_mock_interview(self.selected_vacancy_id)
        if saved_chat:
            self.mock_chat_history = saved_chat
            self._render_mock_chat()
        else:
            self.mock_chat_history = []
            self.view.interview_tab.chat_arena.controls.clear()
            
        self.page.update()

    def handle_search(self, e):
        scout_tab = self.view.scout_tab
        keyword = scout_tab.input_keyword.value
        period = scout_tab.combo_period.value
        experience = scout_tab.combo_exp.value
        area = scout_tab.combo_area.value
        schedule = scout_tab.combo_schedule.value
        
        thread = threading.Thread(target=self.run_search_in_thread, args=(keyword, period, experience, area, schedule))
        thread.start()

    def run_search_in_thread(self, keyword, period, experience, area, schedule):
        parser = HHParser()
        vacancies = parser.parse_market(
            text=keyword, period=period, experience=experience, 
            area=area, schedule=schedule, page_limit=1
        )
        self.repo.save_vacancies(vacancies)
        self.page.run_thread(self.refresh_table_data)

    def handle_generation(self, e):
        if not self.selected_vacancy_id:
            self.show_error_dialog("Вакансия не выбрана.")
            return
        
        v_data = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        
        try:
            resume_text = self.resume.extract_text()
            response = self.analyzer.generate_cover_letter(resume_text, v_data['title'], v_data['company'], v_data['description'])
            
            letter_text = response.get("letter", "").strip()
            recs_text = "\n".join([f"• {r}" for r in response.get("recommendations", [])])

            self.view.letters_tab.text_letter.value = letter_text
            self.view.letters_tab.text_recs.value = recs_text
            
            self.repo.save_cover_letter(self.selected_vacancy_id, letter_text, recs_text)
            if v_data['status'] == 'discovered':
                self.repo.update_status(self.selected_vacancy_id, 'processed')
            
            self.page.go("/letters")
            self.page.update()

        except Exception as ex:
            self.show_error_dialog(f"Ошибка генерации: {ex}")

    def handle_feedback(self, e):
        if not self.selected_vacancy_id:
            self.show_error_dialog("Вакансия не выбрана.")
            return
        
        feedback = self.view.letters_tab.input_feedback.value
        if not feedback:
            return

        v_data = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        current_letter = self.view.letters_tab.text_letter.value

        try:
            response = self.analyzer.adjust_letter(current_letter, feedback, v_data['title'], v_data['description'])
            new_letter = response.get("letter", current_letter).strip()
            
            self.view.letters_tab.text_letter.value = new_letter
            self.view.letters_tab.input_feedback.value = ""
            
            self.repo.save_cover_letter(self.selected_vacancy_id, new_letter, self.view.letters_tab.text_recs.value)
            self.page.update()
        except Exception as ex:
            self.show_error_dialog(f"Ошибка обратной связи: {ex}")

    def handle_auto_apply(self, e):
        if not self.selected_vacancy_id:
            self.show_error_dialog("Вакансия не выбрана.")
            return
        
        letter_text = self.view.letters_tab.text_letter.value
        if not letter_text:
            self.show_error_dialog("Сопроводительное письмо не может быть пустым.")
            return

        thread = threading.Thread(target=self.run_auto_apply_in_thread, args=(self.selected_vacancy_id, letter_text))
        thread.start()

    def run_auto_apply_in_thread(self, vacancy_id, letter_text):
        parser = HHParser()
        success, msg = parser.auto_apply(vacancy_id, letter_text)
        
        if success:
            self.repo.update_status(vacancy_id, "applied")
            self.page.run_thread(self.refresh_table_data)
            self.show_info_dialog("Успех", msg)
        else:
            self.show_error_dialog(msg)

    def handle_start_mock(self, e):
        if not self.selected_vacancy_id:
            self.show_error_dialog("Вакансия не выбрана.")
            return

        v_data = self.repo.get_vacancy_by_id(self.selected_vacancy_id)
        
        system_instruction = (
            f"Ты — строгий Senior QA Automation / Team Lead в компании {v_data['company']}. "
            f"Ты проводишь technical interview с кандидатом на позицию '{v_data['title']}'. "
            f"Требования вакансии:\n{v_data['description']}\n\n"
            "Инструкция: Представься и задай ОДИН конкретный глубокий технический вопрос по стеку вакансии. Не пиши за соискателя."
        )
        self.mock_chat_history = [{"role": "system", "content": system_instruction}]
        
        try:
            first_question = self.analyzer.generate_mock_reply(self.mock_chat_history)
            self.mock_chat_history.append({"role": "assistant", "content": first_question})
            self._render_mock_chat()
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
        except Exception as ex:
            self.show_error_dialog(f"Ошибка начала собеседования: {ex}")

    def handle_send_chat(self, e):
        user_text = self.view.interview_tab.input_chat.value
        if not user_text or not self.mock_chat_history:
            return

        self.mock_chat_history.append({"role": "user", "content": user_text})
        self.view.interview_tab.input_chat.value = ""
        self._render_mock_chat()
        
        try:
            next_prompt = "Оцени ответ по 10-балльной шкале, укажи ошибки. Задай следующий точечный вопрос по стеку."
            messages = list(self.mock_chat_history)
            messages.append({"role": "system", "content": next_prompt})

            ai_feedback = self.analyzer.generate_mock_reply(messages)
            self.mock_chat_history.append({"role": "assistant", "content": ai_feedback})
            self._render_mock_chat()
            self.repo.save_mock_interview(self.selected_vacancy_id, self.mock_chat_history)
        except Exception as ex:
            self.show_error_dialog(f"Ошибка отправки сообщения: {ex}")

    def handle_reset_mock(self, e):
        self.mock_chat_history = []
        if self.selected_vacancy_id:
            self.repo.save_mock_interview(self.selected_vacancy_id, [])
        self.view.interview_tab.chat_arena.controls.clear()
        self.page.update()

    def _render_mock_chat(self):
        chat_arena = self.view.interview_tab.chat_arena
        chat_arena.controls.clear()
        for msg in self.mock_chat_history:
            if msg["role"] == "assistant":
                chat_arena.controls.append(ft.Text(f"Тимлид: {msg['content']}", selectable=True))
            elif msg["role"] == "user":
                chat_arena.controls.append(ft.Text(f"Вы: {msg['content']}", selectable=True, color="cyan"))
        self.page.update()

    def draw_analytics_chart(self, e):
        vacancies = self.repo.get_vacancies_filtered("all")
        market_salaries = [v['salary_min'] for v in vacancies if v.get('salary_min')]
        
        if not market_salaries:
            self.show_info_dialog("Нет данных", "Нет данных о зарплатах для построения графика.")
            return

        fig = Figure()
        ax = fig.add_subplot(111)
        ax.hist(market_salaries, bins=20, color='skyblue', edgecolor='black')
        ax.set_title('Распределение зарплат')
        ax.set_xlabel('Зарплата')
        ax.set_ylabel('Количество вакансий')
        
        chart_path = "data/chart.png"
        fig.savefig(chart_path)
        
        self.view.analytics_tab.chart_image.src = chart_path
        self.page.update()

    def show_error_dialog(self, message):
        dlg = ft.AlertDialog(title=ft.Text("Ошибка"), content=ft.Text(message))
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()

    def show_info_dialog(self, title, message):
        dlg = ft.AlertDialog(title=ft.Text(title), content=ft.Text(message))
        self.page.dialog = dlg
        dlg.open = True
        self.page.update()
