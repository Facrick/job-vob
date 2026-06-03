import flet as ft
from gui.components import primary_btn, secondary_btn, card, GAP

class HandbookTabView:
    def __init__(self, controller):
        self.controller = controller
        self.search_field = ft.TextField(hint_text="Поиск по темам...", dense=True,
                                         prefix_icon=ft.Icons.SEARCH,
                                         on_change=controller.handle_handbook_search)

        _MODES = [
            ("sections",  ft.Icons.MENU_BOOK,  "Разделы"),
            ("favorites", ft.Icons.STAR,        "Избранное"),
            ("plan",      ft.Icons.CHECKLIST,   "План"),
            ("quiz",      ft.Icons.PSYCHOLOGY,  "Квиз"),
        ]

        # Горизонтальный скроллируемый ряд кнопок режимов.
        # SegmentedButton не используется — он не скроллируется и рендерится
        # колесом при нехватке ширины в Flet 0.85.
        self._mode_btns: dict[str, ft.TextButton] = {}
        self.mode_bar = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=2)
        for val, icon, label in _MODES:
            btn = ft.TextButton(
                content=ft.Row(
                    [ft.Icon(icon, size=16), ft.Text(label, size=12)],
                    spacing=4, tight=True,
                ),
                on_click=lambda e, m=val: controller.set_handbook_mode(m),
            )
            self._mode_btns[val] = btn
            self.mode_bar.controls.append(btn)
        self.set_active_mode("sections")

        self.progress_label = ft.Text("Прогресс 0% (0 из 0)", size=11, color=ft.Colors.ON_SURFACE_VARIANT)
        self.progress_bar = ft.ProgressBar(value=0, color=ft.Colors.GREEN_500)

        self.tree_handbook = ft.ListView(expand=True, spacing=2, padding=4)
        self.text_handbook = ft.Markdown(value="Выберите вопрос в списке слева, чтобы увидеть ответ.",
                                         selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        self.topic_title = ft.Text("", weight=ft.FontWeight.BOLD, size=15)
        self.topic_badge = ft.Text("", size=11, color=ft.Colors.AMBER_400)
        self.btn_studied = ft.IconButton(icon=ft.Icons.CHECK_CIRCLE_OUTLINE, visible=False,
                                         tooltip="Отметить изученным",
                                         on_click=controller.handle_handbook_studied)
        self.btn_fav = ft.IconButton(icon=ft.Icons.STAR_BORDER, visible=False, tooltip="В избранное",
                                     on_click=controller.handle_handbook_favorite)
        self.btn_edit = secondary_btn("Редактировать", controller.handle_handbook_edit, icon=ft.Icons.EDIT)
        self.btn_edit.visible = False
        self.editor = ft.TextField(multiline=True, expand=True, min_lines=10,
                                   border_color=ft.Colors.OUTLINE_VARIANT)
        self.instr_field = ft.TextField(
            hint_text="Что поправить? напр. «добавь пример кода и кратко про плюсы/минусы»",
            dense=True, expand=True)
        self.btn_ai_fix = secondary_btn("Поправить ИИ", controller.handle_handbook_ai_fix,
                                        icon=ft.Icons.AUTO_AWESOME)
        self.btn_save   = primary_btn("Сохранить", controller.handle_handbook_save, icon=ft.Icons.SAVE)
        self.btn_cancel = secondary_btn("Отмена", controller.handle_handbook_cancel, icon=ft.Icons.CLOSE)
        self.view_box = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, controls=[self.text_handbook])
        self.edit_box = ft.Column(expand=True, spacing=8, visible=False, controls=[
            ft.Text("Текст ответа (обычный текст / Markdown — заголовки ###, списки -, код в ```):",
                    size=11, color=ft.Colors.ON_SURFACE_VARIANT),
            self.editor,
            ft.Row([self.instr_field, self.btn_ai_fix], spacing=8),
            ft.Row([self.btn_save, self.btn_cancel], spacing=8),
        ])

        # Квиз — AI-driven session
        self.quiz_scope = ft.Dropdown(
            label="Тема квиза", value="all", dense=True, width=200,
            options=[
                ft.DropdownOption(key="all", text="Все темы"),
                ft.DropdownOption(key="favorites", text="Только избранное"),
            ]
        )
        self.btn_quiz_start = primary_btn("Начать квиз", controller.handle_quiz_start, icon=ft.Icons.PLAY_ARROW)
        self.btn_quiz_next = primary_btn("Следующий вопрос", controller.handle_quiz_next, icon=ft.Icons.SKIP_NEXT)
        self.btn_quiz_next.visible = False
        self.quiz_progress_label = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.quiz_question_text = ft.Text("", size=16, weight=ft.FontWeight.W_600, selectable=True)
        self.quiz_answer_input = ft.TextField(
            label="Ваш ответ", multiline=True, min_lines=4, max_lines=10, expand=True,
            visible=False,
        )
        self.btn_quiz_check = primary_btn("Проверить ответ", controller.handle_quiz_check, icon=ft.Icons.AUTO_AWESOME)
        self.btn_quiz_check.visible = False
        self.quiz_spinner = ft.ProgressRing(visible=False, width=24, height=24)
        self.quiz_eval_chip = ft.Chip(label=ft.Text(""), visible=False)
        self.quiz_feedback_text = ft.Markdown("", selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, visible=False)
        self.quiz_correct_answer = ft.Markdown("", selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB, visible=False)
        self.quiz_correct_label = ft.Text("📖 Правильный ответ из учебника:", size=13, weight=ft.FontWeight.W_600, color=ft.Colors.INDIGO_200, visible=False)

        self.quiz_box = ft.Column(expand=True, spacing=15, visible=False, scroll=ft.ScrollMode.AUTO, controls=[
            # Setup row
            ft.Row([self.quiz_scope, self.btn_quiz_start, ft.Container(expand=True), self.quiz_progress_label, self.quiz_spinner], spacing=8),
            ft.Divider(),
            # Question
            self.quiz_question_text,
            # Answer input
            self.quiz_answer_input,
            ft.Row([self.btn_quiz_check, self.btn_quiz_next], spacing=8),
            # Result
            self.quiz_eval_chip,
            self.quiz_feedback_text,
            ft.Divider(visible=False),  # shown after evaluation
            self.quiz_correct_label,
            self.quiz_correct_answer,
        ])

        # Панель темы (персистентна)
        self.topic_pane = ft.Column(expand=True, spacing=8, controls=[
            ft.Row([self.topic_title, self.topic_badge, ft.Container(expand=True),
                    self.btn_studied, self.btn_fav, self.btn_edit],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1),
            self.view_box, self.edit_box,
        ])

    def set_active_mode(self, mode: str):
        """Подсвечивает активную кнопку режима, сбрасывает остальные."""
        _ACTIVE = ft.ButtonStyle(
            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.INDIGO_300),
            color=ft.Colors.INDIGO_200,
        )
        for val, btn in self._mode_btns.items():
            btn.style = _ACTIVE if val == mode else None

    def build(self, wide: bool = True) -> ft.Control:
        left = card(ft.Column(expand=True, spacing=8, controls=[
            self.mode_bar,
            self.progress_label, self.progress_bar, self.search_field,
            self.tree_handbook,
        ]), expand=True, padding=10)
        right = card(ft.Column(expand=True, controls=[self.topic_pane, self.quiz_box]), expand=True)
        if wide:
            return ft.Row(expand=True, spacing=GAP, controls=[
                ft.Container(width=340, content=left), right,
            ])
        return ft.Column(expand=True, spacing=GAP, controls=[
            ft.Container(height=240, content=left), right,
        ])
