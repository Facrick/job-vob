class HandbookTabView:
    def __init__(self, controller):
        self.controller = controller
        self.search_field = ft.TextField(hint_text="Поиск по темам...", dense=True,
                                         prefix_icon=ft.Icons.SEARCH,
                                         on_change=controller.handle_handbook_search)
        self.btn_mode_sections = ft.TextButton(content=ft.Text("Разделы"), icon=ft.Icons.MENU_BOOK,
                                               on_click=lambda e: controller.set_handbook_mode("sections"))
        self.btn_mode_fav = ft.TextButton(content=ft.Text("Избранное"), icon=ft.Icons.STAR,
                                          on_click=lambda e: controller.set_handbook_mode("favorites"))
        self.btn_mode_plan = ft.TextButton(content=ft.Text("План"), icon=ft.Icons.CHECKLIST,
                                           on_click=lambda e: controller.set_handbook_mode("plan"))
        self.btn_mode_cards = ft.TextButton(content=ft.Text("Карточки"), icon=ft.Icons.STYLE,
                                            on_click=lambda e: controller.set_handbook_mode("cards"))

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

        # Флеш-карточки
        self.cards_scope = ft.Dropdown(label="Что повторяем", value="all", dense=True, options=[
            ft.DropdownOption(key="all",       text="Все темы"),
            ft.DropdownOption(key="favorites", text="Только избранное"),
            ft.DropdownOption(key="unstudied", text="Ещё не изученные"),
        ])
        self.btn_cards_start = primary_btn("Начать", controller.handle_cards_start, icon=ft.Icons.PLAY_ARROW)
        self.cards_controls = ft.Column(visible=False, spacing=10, controls=[
            ft.Text("Режим повторения карточками", weight=ft.FontWeight.W_600),
            self.cards_scope, self.btn_cards_start,
        ])
        self.card_progress = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        self.card_question = ft.Text("Выберите область и нажмите «Начать».", size=18, weight=ft.FontWeight.BOLD)
        self.btn_reveal = primary_btn("Показать ответ", controller.handle_cards_reveal, icon=ft.Icons.VISIBILITY)
        self.btn_reveal.visible = False
        self.card_answer = ft.Markdown("", selectable=True, extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)
        self.card_answer_box = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO, visible=False,
                                         controls=[self.card_answer])
        self.btn_know = primary_btn("Знаю", controller.handle_cards_know, icon=ft.Icons.CHECK,
                                    bgcolor=ft.Colors.GREEN, color=ft.Colors.WHITE)
        self.btn_repeat = secondary_btn("Повторить", controller.handle_cards_repeat, icon=ft.Icons.REFRESH)
        self.card_actions = ft.Row([self.btn_know, self.btn_repeat], spacing=8, visible=False)
        self.card_box = ft.Column(expand=True, spacing=12, visible=False, controls=[
            self.card_progress,
            ft.Container(content=self.card_question, padding=ft.Padding(0, 20, 0, 8)),
            self.btn_reveal, self.card_answer_box, self.card_actions,
        ])

        # Панель темы (персистентна)
        self.topic_pane = ft.Column(expand=True, spacing=8, controls=[
            ft.Row([self.topic_title, self.topic_badge, ft.Container(expand=True),
                    self.btn_studied, self.btn_fav, self.btn_edit],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1),
            self.view_box, self.edit_box,
        ])

    def build(self, wide: bool = True) -> ft.Control:
        left = card(ft.Column(expand=True, spacing=8, controls=[
            ft.Row([self.btn_mode_sections, self.btn_mode_fav, self.btn_mode_plan, self.btn_mode_cards],
                   scroll=ft.ScrollMode.AUTO, spacing=2),
            self.progress_label, self.progress_bar, self.search_field,
            self.tree_handbook, self.cards_controls,
        ]), expand=True, padding=10)
        right = card(ft.Column(expand=True, controls=[self.topic_pane, self.card_box]), expand=True)
        if wide:
            return ft.Row(expand=True, spacing=GAP, controls=[
                ft.Container(width=340, content=left), right,
            ])
        return ft.Column(expand=True, spacing=GAP, controls=[
            ft.Container(height=240, content=left), right,
        ])


# ──────────────────────────────────────────────────────────────
#  Вкладка 6 — Логи
# ──────────────────────────────────────────────────────────────