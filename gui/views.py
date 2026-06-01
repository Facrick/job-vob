import tkinter as tk
import customtkinter as ctk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from typing import Dict, List, Callable, Optional

from gui.theme import PERIOD_MAP, EXPERIENCE_MAP

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class KanbanCard(ctk.CTkFrame):
    def __init__(self, vacancy_data: Dict, main_window, parent=None):
        super().__init__(
            parent, corner_radius=10, fg_color="#111827",
            border_color="#1f2937", border_width=1,
        )
        self.data = vacancy_data
        self.main_window = main_window
        self._init_ui()

    def _init_ui(self):
        self.configure(width=190, height=115)
        self.pack_propagate(False)
        content_frame = ctk.CTkFrame(self, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.lbl_company = ctk.CTkLabel(
            content_frame,
            text=self.data.get("company", "Не указана").upper(),
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#34d399", anchor="w",
        )
        self.lbl_company.pack(fill="x", side="top")

        self.lbl_title = ctk.CTkLabel(
            content_frame,
            text=self.data.get("title", "Без названия"),
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#ffffff", justify="left", anchor="w", wraplength=165,
        )
        self.lbl_title.pack(fill="x", side="top", pady=(4, 0))

        self.lbl_salary = ctk.CTkLabel(
            content_frame,
            text=self._format_salary(),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#9ca3af", anchor="w",
        )
        self.lbl_salary.pack(fill="x", side="bottom")

        for widget in [self, content_frame, self.lbl_company, self.lbl_title, self.lbl_salary]:
            widget.bind("<Button-1>", self.on_start_drag)

    def _format_salary(self) -> str:
        salary_min = self.data.get("salary_min")
        salary_max = self.data.get("salary_max")
        if salary_min and salary_max:
            return f"{salary_min:,} – {salary_max:,} ₽".replace(",", " ")
        elif salary_min:
            return f"от {salary_min:,} ₽".replace(",", " ")
        elif salary_max:
            return f"до {salary_max:,} ₽".replace(",", " ")
        return "З/П не указана"

    def on_start_drag(self, event):
        self.main_window.controller.select_kanban_card(self.data.get("id"))
        self.main_window.set_current_card(self)
        self.configure(border_color="#38bdf8", border_width=2)


class KanbanColumn(ctk.CTkFrame):
    def __init__(self, title: str, status_id: str, controller, main_window, parent=None):
        super().__init__(
            parent, corner_radius=12, fg_color="#030712",
            border_color="#1f2937", border_width=1,
        )
        self.title_text = title
        self.status_id = status_id
        self.controller = controller
        self.main_window = main_window
        self.cards: List[KanbanCard] = []
        self._init_ui()

    def _init_ui(self):
        self.lbl_title = ctk.CTkLabel(
            self, text=f"{self.title_text} (0)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#9ca3af",
        )
        self.lbl_title.pack(fill="x", padx=8, pady=8)

        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent", height=550)
        self.scroll_frame.pack(fill="both", expand=True, padx=4, pady=4)

    def clear_cards(self):
        for card in self.cards:
            card.destroy()
        self.cards.clear()
        self.lbl_title.configure(text=f"{self.title_text} (0)")

    def add_card(self, vacancy_data: Dict):
        card = KanbanCard(vacancy_data, self.main_window, parent=self.scroll_frame)
        card.pack(fill="x", padx=4, pady=4)
        self.cards.append(card)
        self.lbl_title.configure(text=f"{self.title_text} ({len(self.cards)})")


class MainWindow(ctk.CTk):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.active_card: Optional[KanbanCard] = None
        self.handbook_sections: List[Dict] = []

        self.title("QA Smart Assistant Pro")
        self.geometry("1440x900")
        self.minsize(1200, 700)

        self._init_ui()

    def _init_ui(self):
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True, padx=16, pady=16)

        self.tabs_bar = ctk.CTkSegmentedButton(
            self.main_container,
            values=["Канбан Воронка", "Письма", "Собеседования", "Графики з/п", "Учебник QA", "Логи"],
            command=self.on_tab_changed,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
        )
        self.tabs_bar.pack(fill="x", side="top", pady=(0, 14))

        self.content_pane = ctk.CTkFrame(
            self.main_container, fg_color="#0b0f19", corner_radius=12,
            border_color="#1f2937", border_width=1,
        )
        self.content_pane.pack(fill="both", expand=True)

        self.frames = {
            "scout": ctk.CTkFrame(self.content_pane, fg_color="transparent"),
            "letters": ctk.CTkFrame(self.content_pane, fg_color="transparent"),
            "interview": ctk.CTkFrame(self.content_pane, fg_color="transparent"),
            "analytics": ctk.CTkFrame(self.content_pane, fg_color="transparent"),
            "handbook": ctk.CTkFrame(self.content_pane, fg_color="transparent"),
            "logs": ctk.CTkFrame(self.content_pane, fg_color="transparent"),
        }

        self.setup_scout_tab()
        self.setup_letters_tab()
        self.setup_interview_tab()
        self.setup_analytics_tab()
        self.setup_handbook_tab()
        self.setup_logs_tab()

        self.tabs_bar.set("Канбан Воронка")
        self.on_tab_changed("Канбан Воронка")

    def on_tab_changed(self, value: str):
        mapping = {
            "Канбан Воронка": "scout",
            "Письма": "letters",
            "Собеседования": "interview",
            "Графики з/п": "analytics",
            "Учебник QA": "handbook",
            "Логи": "logs",
        }
        for frame in self.frames.values():
            frame.pack_forget()
        self.frames[mapping[value]].pack(fill="both", expand=True, padx=12, pady=12)

    # ================================================================== #
    #  ПУБЛИЧНЫЙ ФАСАД ДЛЯ КОНТРОЛЛЕРА                                    #
    #  Контроллер вызывает только эти методы и не знает про виджеты.     #
    # ================================================================== #

    @staticmethod
    def _set_textbox(widget: ctk.CTkTextbox, text: str):
        widget.delete("1.0", "end")
        widget.insert("1.0", text or "")

    # --- Канбан ---
    def render_kanban(self, vacancies: List[Dict]):
        for col in self.columns.values():
            col.clear_cards()
        for v in vacancies:
            status = v.get("status", "discovered")
            if status in self.columns:
                self.columns[status].add_card(v)

    # --- Поиск ---
    def get_search_keyword(self) -> str:
        return self.input_keyword.get().strip()

    def get_search_filters(self) -> tuple:
        """Возвращает (period_days, experience_api) из комбобоксов.

        Маппит человекочитаемые значения UI в параметры API hh.ru.
        Раньше эти комбобоксы были декоративными.
        """
        period = PERIOD_MAP.get(self.combo_period.get(), 7)
        experience = EXPERIENCE_MAP.get(self.combo_exp.get(), "between1And3")
        return period, experience

    def set_search_in_progress(self, in_progress: bool):
        if in_progress:
            self.btn_search.configure(state="disabled")
            self.progress_bar.pack(fill="x", side="top", pady=4)
            self.progress_bar.set(0.1)
        else:
            self.btn_search.configure(state="normal")
            self.progress_bar.pack_forget()

    # --- Карточка вакансии ---
    def show_vacancy(self, vacancy: Dict):
        self.label_active_vacancy.configure(
            text=f"💼 {vacancy['company']} | {vacancy['title']}"
        )
        self._set_textbox(self.text_vacancy_details, vacancy.get("description", ""))
        self._set_textbox(self.text_vacancy_skills, vacancy.get("skills", ""))
        self._set_textbox(self.text_vacancy_notes, vacancy.get("notes", ""))
        self.btn_open_browser.configure(state="normal")
        self.btn_generate_letter.configure(state="normal")

    def get_current_notes(self) -> Optional[str]:
        if hasattr(self, "text_vacancy_notes"):
            return self.text_vacancy_notes.get("1.0", "end-1c").strip()
        return None

    # --- Письма ---
    def show_letter(self, letter: str, recs: str):
        self._set_textbox(self.text_letter, letter)
        self._set_textbox(self.text_recs, recs)

    def get_letter_text(self) -> str:
        return self.text_letter.get("1.0", "end-1c")

    def get_recs_text(self) -> str:
        return self.text_recs.get("1.0", "end-1c")

    def get_feedback_text(self) -> str:
        return self.input_feedback.get().strip()

    def clear_feedback_input(self):
        self.input_feedback.delete(0, "end")

    def set_generate_enabled(self, enabled: bool):
        self.btn_generate_letter.configure(state="normal" if enabled else "disabled")

    def set_auto_apply_enabled(self, enabled: bool):
        self.btn_auto_apply.configure(state="normal" if enabled else "disabled")

    def switch_to_letters_tab(self):
        self.tabs_bar.set("Письма")
        self.on_tab_changed("Письма")

    # --- Учебник ---
    def show_handbook_answer(self, text: str):
        self._set_textbox(self.text_handbook, text)

    # --- Чат / mock-интервью ---
    def get_chat_input(self) -> str:
        return self.input_chat.get().strip()

    def clear_chat_input(self):
        self.input_chat.delete(0, "end")

    def clear_chat(self):
        for widget in self.chat_scroll.winfo_children():
            widget.destroy()

    def render_chat(self, history: List[Dict]):
        for msg in history:
            if msg["role"] in ("user", "assistant"):
                self.append_chat_bubble(msg["role"], msg["content"])

    # --- Аналитика ---
    def draw_salary_charts(self, my_salary: int, current_salary: int, market_salaries: list):
        self.fig.clear()
        ax1 = self.fig.add_subplot(121)
        ax1.set_facecolor("#181825")
        ax1.set_title("Сравнение зарплат", color="white")
        ax1.bar(
            ["Мои ожидания", "Вакансия"],
            [my_salary, current_salary],
            color=["#a6e3a1", "#f38ba8"],
        )
        ax1.tick_params(colors="white")

        ax2 = self.fig.add_subplot(122)
        ax2.set_facecolor("#181825")
        ax2.set_title("Распределение зарплат на рынке", color="white")
        ax2.hist(market_salaries, bins=15, color="#38bdf8", edgecolor="white")
        ax2.tick_params(colors="white")

        self.fig.tight_layout()
        self.canvas.draw()

    # ================================================================== #
    #  ПОСТРОЕНИЕ ВКЛАДОК                                                 #
    # ================================================================== #

    def setup_scout_tab(self):
        frame = self.frames["scout"]

        filter_box = ctk.CTkFrame(frame, fg_color="transparent")
        filter_box.pack(fill="x", side="top", pady=(0, 10))

        self.input_keyword = ctk.CTkEntry(filter_box, placeholder_text="Ключевое слово", width=160)
        self.input_keyword.insert(0, "QA Engineer")
        self.input_keyword.pack(side="left", padx=4)

        self.combo_period = ctk.CTkComboBox(
            filter_box, values=["За сутки", "За 3 дня", "За неделю", "За месяц"], width=120
        )
        self.combo_period.set("За неделю")
        self.combo_period.pack(side="left", padx=4)

        self.combo_exp = ctk.CTkComboBox(
            filter_box, values=["1–3 года", "Без опыта", "3–6 лет"], width=120
        )
        self.combo_exp.set("1–3 года")
        self.combo_exp.pack(side="left", padx=4)

        self.btn_search = ctk.CTkButton(
            filter_box, text="🔍 Собрать", width=90, command=self.controller.handle_search
        )
        self.btn_search.pack(side="left", padx=4)

        action_box = ctk.CTkFrame(
            frame, fg_color="#11111b", height=54, corner_radius=8,
            border_color="#1e1e2e", border_width=1,
        )
        action_box.pack(fill="x", side="top", pady=(0, 10))

        self.label_active_vacancy = ctk.CTkLabel(
            action_box, text="Выберите вакансию...",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#38bdf8", anchor="w",
        )
        self.label_active_vacancy.pack(side="left", padx=14, fill="y")

        self.btn_export = ctk.CTkButton(
            action_box, text="📊 Слить базу", fg_color="#10b981", width=110,
            command=self.controller.handle_export,
        )
        self.btn_export.pack(side="right", padx=8, pady=10)

        self.btn_generate_letter = ctk.CTkButton(
            action_box, text="✨ ИИ-Письмо", width=110,
            command=self.controller.handle_generation,
        )
        self.btn_generate_letter.pack(side="right", padx=8, pady=10)

        self.btn_open_browser = ctk.CTkButton(
            action_box, text="🔗 На hh.ru", width=110,
            command=self.controller.open_vacancy_in_browser,
        )
        self.btn_open_browser.pack(side="right", padx=8, pady=10)

        self.progress_bar = ctk.CTkProgressBar(frame, height=4)
        self.progress_bar.pack_forget()

        workspace = ctk.CTkFrame(frame, fg_color="transparent")
        workspace.pack(fill="both", expand=True)

        self.kanban_box = ctk.CTkFrame(workspace, fg_color="transparent")
        self.kanban_box.pack(side="left", fill="both", expand=True)

        self.columns = {
            sid: KanbanColumn(title, sid, self.controller, self, parent=self.kanban_box)
            for title, sid in [
                ("Новые", "discovered"),
                ("Письмо готово", "processed"),
                ("Отклик отправлен", "applied"),
                ("Собеседование", "interview"),
                ("Оффер!", "offer"),
                ("Отказ", "rejected"),
            ]
        }
        for col in self.columns.values():
            col.pack(side="left", fill="both", expand=True, padx=3)

        self.details_container = ctk.CTkFrame(
            workspace, width=310, fg_color="#11111b", corner_radius=10,
            border_color="#1e1e2e", border_width=1,
        )
        self.details_container.pack(side="right", fill="both", expand=False)

        self.text_vacancy_details = ctk.CTkTextbox(
            self.details_container, fg_color="#030712", font=("Segoe UI", 12)
        )
        self.text_vacancy_details.pack(fill="both", expand=True, padx=10, pady=4)

        self.text_vacancy_skills = ctk.CTkTextbox(
            self.details_container, fg_color="#030712", height=80,
            font=("Segoe UI", 12), text_color="#34d399",
        )
        self.text_vacancy_skills.pack(fill="x", padx=10, pady=4)

        self.text_vacancy_notes = ctk.CTkTextbox(
            self.details_container, fg_color="#030712", height=80,
            font=("Segoe UI", 12), text_color="#f3f4f6",
        )
        self.text_vacancy_notes.pack(fill="x", padx=10, pady=10)

    def set_current_card(self, card: KanbanCard):
        if self.active_card and self.active_card.winfo_exists():
            self.active_card.configure(border_color="#1f2937", border_width=1)
        self.active_card = card
        if card and card.winfo_exists():
            card.configure(border_color="#38bdf8", border_width=2)

    def setup_letters_tab(self):
        frame = self.frames["letters"]
        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="both", expand=True)

        left = ctk.CTkFrame(content, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True)

        self.text_letter = ctk.CTkTextbox(left, fg_color="#030712", font=("Consolas", 14))
        self.text_letter.pack(fill="both", expand=True)

        f_box = ctk.CTkFrame(left, fg_color="transparent")
        f_box.pack(fill="x", pady=5)

        self.input_feedback = ctk.CTkEntry(f_box, placeholder_text="Правки...")
        self.input_feedback.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(f_box, text="🛠️ Исправить", command=self.controller.handle_feedback).pack(
            side="right", padx=4
        )
        ctk.CTkButton(
            f_box, text="📋 Копировать", fg_color="#4b5563",
            command=self.copy_letter_to_clipboard,
        ).pack(side="right")

        self.text_recs = ctk.CTkTextbox(content, fg_color="#030712", width=300)
        self.text_recs.pack(side="right", fill="y", padx=10)

        self.btn_auto_apply = ctk.CTkButton(
            frame, text="🚀 СДЕЛАТЬ ОТКЛИК", fg_color="#10b981", height=44,
            command=self.controller.handle_auto_apply,
        )
        self.btn_auto_apply.pack(fill="x", side="bottom")

    def copy_letter_to_clipboard(self):
        self.clipboard_clear()
        self.clipboard_append(self.text_letter.get("1.0", "end-1c"))
        self.update()

    def setup_interview_tab(self):
        frame = self.frames["interview"]
        self.chat_scroll = ctk.CTkScrollableFrame(frame, fg_color="#030712")
        self.chat_scroll.pack(fill="both", expand=True, pady=6)

        input_box = ctk.CTkFrame(frame, fg_color="transparent")
        input_box.pack(fill="x", pady=6)

        self.input_chat = ctk.CTkEntry(input_box, placeholder_text="Ваш ответ...")
        self.input_chat.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(input_box, text="Отправить", command=self.controller.handle_send_chat).pack(
            side="right", padx=5
        )

        ctrls = ctk.CTkFrame(frame, fg_color="transparent")
        ctrls.pack(fill="x")
        ctk.CTkButton(ctrls, text="🚀 Запустить", command=self.controller.handle_start_mock).pack(
            side="left", fill="x", expand=True
        )
        ctk.CTkButton(
            ctrls, text="🔄 Сбросить", fg_color="#f38ba8",
            command=self.controller.handle_reset_mock,
        ).pack(side="right")

    def append_chat_bubble(self, sender: str, message: str):
        bubble_frame = ctk.CTkFrame(self.chat_scroll, fg_color="transparent")
        bubble_frame.pack(fill="x", padx=8, pady=4)

        box = ctk.CTkFrame(
            bubble_frame,
            fg_color="#1e1e2e" if sender == "assistant" else "#2563eb",
            corner_radius=12,
        )
        box.pack(
            side="left" if sender == "assistant" else "right",
            anchor="w" if sender == "assistant" else "e",
        )

        label = ctk.CTkLabel(box, text=message, justify="left", wraplength=500)
        label.pack(padx=14, pady=10)

    def setup_analytics_tab(self):
        frame = self.frames["analytics"]
        ctk.CTkButton(
            frame, text="📈 Расчет графиков", command=self.controller.draw_analytics_chart
        ).pack(fill="x")

        self.fig = Figure(figsize=(10, 5), dpi=100)
        self.fig.patch.set_facecolor("#0b0f19")
        self.canvas_container = tk.Frame(frame, bg="#0b0f19")
        self.canvas_container.pack(fill="both", expand=True)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.canvas_container)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def setup_handbook_tab(self):
        frame = self.frames["handbook"]

        left_container = ctk.CTkFrame(frame, fg_color="transparent")
        left_container.pack(side="left", fill="both", expand=True)

        self.handbook_h_scroll = ctk.CTkScrollableFrame(
            left_container, fg_color="transparent", orientation="horizontal"
        )
        self.handbook_h_scroll.pack(fill="both", expand=True)

        self.handbook_content = ctk.CTkFrame(self.handbook_h_scroll, fg_color="transparent")
        self.handbook_content.pack(fill="both", expand=True)

        search_frame = ctk.CTkFrame(self.handbook_content, fg_color="transparent")
        search_frame.pack(fill="x", pady=(0, 10))
        self.search_entry = ctk.CTkEntry(search_frame, placeholder_text="🔍 Поиск...")
        self.search_entry.pack(fill="x")
        self.search_entry.bind("<KeyRelease>", self.on_handbook_search)

        self.tree_frame = ctk.CTkScrollableFrame(self.handbook_content, fg_color="#0b0f19")
        self.tree_frame.pack(fill="both", expand=True)

        self.text_handbook = ctk.CTkTextbox(
            frame, fg_color="#030712", font=("Segoe UI", 14), wrap="word"
        )
        self.text_handbook.pack(side="right", fill="both", expand=True, padx=(10, 0))

    def load_handbook_data_custom(self, sections_dict: Dict, click_callback: Callable):
        for widget in self.tree_frame.winfo_children():
            widget.destroy()
        self.handbook_sections.clear()

        wrap_width = 600

        for section_name, questions in sections_dict.items():
            sec_container = ctk.CTkFrame(self.tree_frame, fg_color="transparent")
            sec_container.pack(fill="x", pady=2)

            lbl_header = ctk.CTkLabel(
                sec_container, text=f"▼ {section_name}",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                anchor="w", wraplength=wrap_width, justify="left",
            )
            lbl_header.pack(fill="x")

            content_frame = ctk.CTkFrame(sec_container, fg_color="transparent")
            content_frame.pack(fill="x", padx=15)

            lbl_header.bind(
                "<Button-1>",
                lambda e, cf=content_frame, lbl=lbl_header, name=section_name:
                    self.toggle_section(cf, lbl, name),
            )

            question_buttons = []
            for q in questions:
                lbl_q = ctk.CTkLabel(
                    content_frame, text=f"• {q['question']}",
                    font=ctk.CTkFont(family="Segoe UI", size=13),
                    anchor="w", wraplength=wrap_width - 30, justify="left",
                )
                lbl_q.pack(fill="x", pady=2)
                lbl_q.bind("<Button-1>", lambda e, qd=q: click_callback(qd))
                question_buttons.append((lbl_q, q["question"].lower()))

            self.handbook_sections.append({
                "container": sec_container,
                "toggle_label": lbl_header,
                "content_frame": content_frame,
                "questions": question_buttons,
                "name": section_name.lower(),
            })

    def toggle_section(self, content_frame: ctk.CTkFrame, label: ctk.CTkLabel, name: str):
        if content_frame.winfo_viewable():
            content_frame.pack_forget()
            label.configure(text=f"▶ {name}")
        else:
            content_frame.pack(fill="x", padx=15)
            label.configure(text=f"▼ {name}")
        self.tree_frame._parent_canvas.update_idletasks()

    def on_handbook_search(self, event=None):
        query = self.search_entry.get().strip().lower()
        for sec in self.handbook_sections:
            visible = 0
            for lbl, q_text in sec["questions"]:
                if query in q_text:
                    lbl.pack(fill="x", pady=2)
                    visible += 1
                else:
                    lbl.pack_forget()

            if visible == 0 and query != "":
                sec["container"].pack_forget()
            else:
                sec["container"].pack(fill="x", pady=2)
                if visible > 0:
                    sec["content_frame"].pack(fill="x", padx=15)
                    sec["toggle_label"].configure(text=f"▼ {sec['name'].title()}")
                else:
                    sec["content_frame"].pack_forget()
                    sec["toggle_label"].configure(text=f"▶ {sec['name'].title()}")
        self.handbook_h_scroll._parent_canvas.update_idletasks()

    def setup_logs_tab(self):
        frame = self.frames["logs"]
        self.text_logs_console = ctk.CTkTextbox(
            frame, fg_color="#010409", font=("Consolas", 12), text_color="#38bdf8"
        )
        self.text_logs_console.pack(fill="both", expand=True)
