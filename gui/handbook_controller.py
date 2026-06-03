import random
import logging

import flet as ft

from core.handbook import AI_SECTION
from core.utils import html_to_markdown

class HandbookController:
    _ACTIVE_BTN_STYLE = ft.ButtonStyle(
        bgcolor=ft.Colors.with_opacity(0.18, ft.Colors.INDIGO_300),
        color=ft.Colors.INDIGO_300,
    )
    _INACTIVE_BTN_STYLE = ft.ButtonStyle(bgcolor=None, color=None)

    def __init__(self, main_controller):
        self.main = main_controller
        self.handbook = self.main.handbook

        self._current_topic: dict | None = None
        self._hb_mode: str = "sections"
        self._deck: list[dict] = []
        self._cards_done: int = 0
        self._handbook_sections: dict = {}

    def load_handbook(self):
        try:
            self._handbook_sections = self.handbook.get_all_sections()
        except Exception as e:
            logging.error(f"Не удалось загрузить учебник: {e}")
            self._handbook_sections = {}
        self._render_handbook("")

    def _tile(self, section_name: str, item: dict) -> ft.Control:
        q = item["question"]
        src = item.get("source", "")
        check = "✓ " if self.handbook.is_studied(q) else ""
        star = "★ " if self.handbook.is_favorite(q) else ""
        badge = "🤖 " if src == "ai" else ("✏️ " if src == "user" else "")
        return ft.ListTile(
            title=ft.Text(
                check + star + badge + q,
                size=13,
                color=ft.Colors.GREEN_300 if check else None,
            ),
            data={
                "section": section_name,
                "question": q,
                "answer": item["answer"],
                "source": src,
            },
            on_click=self._handle_handbook_click,
            dense=True,
            shape=ft.RoundedRectangleBorder(radius=8),
        )

    def _render_progress(self):
        done, total = self.handbook.progress()
        hb = self.main.view.handbook_tab
        hb.progress_bar.value = (done / total) if total else 0
        pct = round(done / total * 100) if total else 0
        hb.progress_label.value = f"Прогресс {pct}% ({done} из {total})"

    def _render_handbook(self, query: str = ""):
        self._render_progress()
        tree = self.main.view.handbook_tab.tree_handbook
        tree.controls.clear()

        if self._hb_mode == "plan":
            self._render_learning_plan(tree)
            if self.main.page:
                self.main.page.update()
            return

        q = (query or "").strip().lower()
        only_fav = self._hb_mode == "favorites"
        for section_name, questions in self._handbook_sections.items():
            sec_match = q in section_name.lower()
            shown = [
                it
                for it in questions
                if (not q or sec_match or q in it.get("question", "").lower())
                and (not only_fav or self.handbook.is_favorite(it["question"]))
            ]
            if not shown:
                continue
            done, total = self.handbook.section_progress(section_name)
            tree.controls.append(
                ft.ExpansionTile(
                    title=ft.Text(
                        f"{section_name}  ({done}/{total})",
                        weight=ft.FontWeight.BOLD,
                        size=14,
                    ),
                    controls=[self._tile(section_name, it) for it in shown],
                    expanded=bool(q) or only_fav,
                )
            )
        if not tree.controls:
            msg = (
                "В избранном пока пусто — отметьте темы ★."
                if only_fav
                else "Ничего не найдено"
            )
            tree.controls.append(
                ft.Text(msg, italic=True, color=ft.Colors.ON_SURFACE_VARIANT)
            )
        if q and not only_fav:
            term = query.strip()
            tree.controls.append(
                ft.TextButton(
                    content=ft.Text(f"Сгенерировать раздел «{term}» с помощью ИИ"),
                    icon=ft.Icons.AUTO_AWESOME,
                    on_click=lambda e, t=term: self._generate_handbook_topic(t),
                )
            )
        if self.main.page:
            self.main.page.update()

    def set_handbook_mode(self, mode: str):
        self._hb_mode = mode
        hb = self.main.view.handbook_tab
        mode_btns = {
            "sections": hb.btn_mode_sections,
            "favorites": hb.btn_mode_fav,
            "plan": hb.btn_mode_plan,
            "cards": hb.btn_mode_cards,
            "quiz": hb.btn_mode_quiz,
        }
        for m, btn in mode_btns.items():
            btn.style = (
                self._ACTIVE_BTN_STYLE if m == mode else self._INACTIVE_BTN_STYLE
            )
            
        is_cards = mode == "cards"
        is_quiz = mode == "quiz"
        
        hb.search_field.visible = not is_cards
        hb.tree_handbook.visible = not is_cards
        hb.cards_controls.visible = is_cards
        
        hb.topic_pane.visible = not is_cards and not is_quiz
        hb.card_box.visible = is_cards
        hb.quiz_box.visible = is_quiz
        
        if is_cards:
            self._deck = []
            hb.card_progress.value = ""
            hb.card_question.value = "Выберите область и нажмите «Начать»."
            hb.btn_reveal.visible = False
            hb.card_answer_box.visible = False
            hb.card_actions.visible = False
            self._render_progress()
            self.main.page.update()
        elif is_quiz:
            if not self._current_topic:
                hb.quiz_question.value = "Выберите тему из списка слева для прохождения квиза."
                hb.quiz_input_box.visible = False
            else:
                self._show_quiz_for_topic(self._current_topic)
            self.main.page.update()
        else:
            self._render_handbook(hb.search_field.value)

    def handle_handbook_search(self, e):
        self._render_handbook(e.control.value)

    def _compute_learning_plan(self) -> list[tuple[str, int]]:
        resume = self.main._safe_resume_text().lower()
        counts: dict[str, int] = {}
        for v in self.main.repo.get_vacancies_filtered("all"):
            for raw in (v.get("skills") or "").split(","):
                skill = raw.strip()
                low = skill.lower()
                if not skill or low in ("не указаны", "не указано") or low in resume:
                    continue
                counts[skill] = counts.get(skill, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])[:25]

    def _render_learning_plan(self, tree):
        plan = self._compute_learning_plan()
        if not plan:
            tree.controls.append(
                ft.Text(
                    "План пуст: соберите вакансии (CRM) и загрузите резюме — "
                    "сюда попадут требуемые навыки, которых нет в резюме.",
                    italic=True,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                )
            )
            return
        tree.controls.append(
            ft.Text(
                "Навыки из ваших вакансий, которых нет в резюме (по частоте):",
                size=12,
                color=ft.Colors.ON_SURFACE_VARIANT,
            )
        )
        for skill, count in plan:
            topic = self.handbook.find_topic(skill)
            if topic:
                section, question, answer, source = topic
                action = ft.TextButton(
                    content=ft.Text("в учебник"),
                    icon=ft.Icons.MENU_BOOK,
                    on_click=lambda e, s=section, q=question, a=answer, sr=source: self._open_handbook_for(
                        s, q, a, sr
                    ),
                )
            else:
                action = ft.TextButton(
                    content=ft.Text("сгенерировать"),
                    icon=ft.Icons.AUTO_AWESOME,
                    on_click=lambda e, t=skill: self._generate_handbook_topic(t),
                )
            tree.controls.append(
                ft.Row(
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    controls=[
                        ft.Container(
                            content=ft.Text(
                                str(count),
                                size=11,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.INDIGO_300,
                            ),
                            bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.INDIGO_300),
                            border_radius=20,
                            padding=ft.Padding(8, 2, 8, 2),
                        ),
                        ft.Text(skill, size=13, expand=True),
                        action,
                    ],
                )
            )

    def handle_handbook_favorite(self, e):
        if not self._current_topic:
            return
        is_fav = self.handbook.toggle_favorite(self._current_topic["question"])
        hb = self.main.view.handbook_tab
        hb.btn_fav.icon = ft.Icons.STAR if is_fav else ft.Icons.STAR_BORDER
        hb.btn_fav.tooltip = "Убрать из избранного" if is_fav else "В избранное"
        self._render_handbook(hb.search_field.value)

    def handle_handbook_studied(self, e):
        if not self._current_topic:
            return
        studied = self.handbook.toggle_studied(self._current_topic["question"])
        hb = self.main.view.handbook_tab
        hb.btn_studied.icon = (
            ft.Icons.CHECK_CIRCLE if studied else ft.Icons.CHECK_CIRCLE_OUTLINE
        )
        hb.btn_studied.tooltip = "Снять отметку" if studied else "Отметить изученным"
        self._render_handbook(hb.search_field.value)

    @staticmethod
    def _is_overlay(source: str) -> bool:
        return source in ("ai", "user")

    def _show_topic(self, section: str, question: str, answer: str, source: str = ""):
        hb = self.main.view.handbook_tab
        self._current_topic = {
            "section": section,
            "question": question,
            "answer": answer,
            "source": source,
        }
        
        if self._hb_mode == "quiz":
            self._show_quiz_for_topic(self._current_topic)
            return

        hb.topic_title.value = question
        hb.topic_badge.value = {
            "ai": "🤖 сгенерировано ИИ — проверьте",
            "user": "✏️ изменено",
        }.get(source, "")
        hb.text_handbook.value = (
            answer if self._is_overlay(source) else html_to_markdown(answer)
        )
        hb.btn_edit.visible = True
        is_fav = self.handbook.is_favorite(question)
        hb.btn_fav.visible = True
        hb.btn_fav.icon = ft.Icons.STAR if is_fav else ft.Icons.STAR_BORDER
        hb.btn_fav.tooltip = "Убрать из избранного" if is_fav else "В избранное"
        is_studied = self.handbook.is_studied(question)
        hb.btn_studied.visible = True
        hb.btn_studied.icon = (
            ft.Icons.CHECK_CIRCLE if is_studied else ft.Icons.CHECK_CIRCLE_OUTLINE
        )
        hb.btn_studied.tooltip = "Снять отметку" if is_studied else "Отметить изученным"
        self._exit_edit_mode()
        
    def _show_quiz_for_topic(self, topic: dict):
        hb = self.main.view.handbook_tab
        hb.quiz_question.value = topic.get("question", "")
        hb.quiz_input.value = ""
        hb.quiz_result.controls.clear()
        hb.quiz_input_box.visible = True
        hb.quiz_btn_check.disabled = False
        hb.quiz_progress.visible = False
        self.main.page.update()

    def _enter_edit_mode(self):
        hb = self.main.view.handbook_tab
        t = self._current_topic or {}
        ans, src = t.get("answer", ""), t.get("source", "")
        hb.editor.value = ans if self._is_overlay(src) else html_to_markdown(ans)
        hb.view_box.visible = False
        hb.edit_box.visible = True
        hb.btn_edit.visible = False

    def _exit_edit_mode(self):
        hb = self.main.view.handbook_tab
        hb.view_box.visible = True
        hb.edit_box.visible = False
        hb.btn_edit.visible = bool(self._current_topic)

    def _handle_handbook_click(self, e):
        d = e.control.data or {}
        self._show_topic(
            d.get("section", ""),
            d.get("question", ""),
            d.get("answer", ""),
            d.get("source", ""),
        )
        self.main.page.update()

    def handle_handbook_edit(self, e):
        if self._current_topic:
            self._enter_edit_mode()
            self.main.page.update()

    def handle_handbook_cancel(self, e):
        self._exit_edit_mode()
        self.main.page.update()

    def handle_handbook_save(self, e):
        if not self._current_topic:
            return
        t = self._current_topic
        new_md = self.main.view.handbook_tab.editor.value or ""
        self.handbook.add_or_update_topic(t["section"], t["question"], new_md, ai=False)
        self._handbook_sections = self.handbook.get_all_sections()
        self._show_topic(t["section"], t["question"], new_md, "user")
        self._render_handbook(self.main.view.handbook_tab.search_field.value)
        self.main._show_info("Сохранено", "Раздел учебника обновлён.")

    def handle_handbook_ai_fix(self, e):
        if not self._current_topic:
            return
        hb = self.main.view.handbook_tab
        current = hb.editor.value or ""
        instructions = hb.instr_field.value or ""
        title = self._current_topic.get("question", "")

        def job():
            revised = self.main.analyzer.revise_handbook_article(
                title, current, instructions
            )
            if revised:
                hb.editor.value = revised
                hb.instr_field.value = ""

        self.main._run_bg(job, busy=hb.btn_ai_fix)

    def handle_handbook_generate(self, e):
        topic = (self.main.view.handbook_tab.search_field.value or "").strip()
        if topic:
            self._generate_handbook_topic(topic)

    def _generate_handbook_topic(self, topic: str, context: str = ""):
        hb = self.main.view.handbook_tab
        hb.text_handbook.value = f"⏳ ИИ пишет раздел «{topic}»..."
        self._exit_edit_mode()
        if self.main.page:
            self.main.page.update()

        def job():
            art = self.main.analyzer.generate_handbook_article(topic, context)
            if not art.get("answer"):
                self.main._show_error(
                    "ИИ не смог сгенерировать материал. Попробуйте ещё раз."
                )
                return
            self.handbook.add_or_update_topic(
                AI_SECTION, art["question"], art["answer"], ai=True
            )
            self._handbook_sections = self.handbook.get_all_sections()
            self._render_handbook("")
            self._show_topic(AI_SECTION, art["question"], art["answer"], "ai")
            self._enter_edit_mode()
            self.main.view.switch_to_tab(self.main.TAB_HANDBOOK)

        self.main._run_bg(job)

    def _open_handbook_for(self, section: str, question: str, answer: str, source: str):
        hb = self.main.view.handbook_tab
        if self._hb_mode != "sections":
            self.set_handbook_mode("sections")
        hb.search_field.value = question
        self._render_handbook(question)
        self._show_topic(section, question, answer, source)
        self.main.view.switch_to_tab(self.main.TAB_HANDBOOK)

    def handle_cards_start(self, e):
        hb = self.main.view.handbook_tab
        scope = hb.cards_scope.value
        deck: list[dict] = []
        for section, items in self.handbook.get_all_sections().items():
            for it in items:
                q = it["question"]
                if scope == "favorites" and not self.handbook.is_favorite(q):
                    continue
                if scope == "unstudied" and self.handbook.is_studied(q):
                    continue
                deck.append(
                    {
                        "section": section,
                        "question": q,
                        "answer": it["answer"],
                        "source": it.get("source", ""),
                    }
                )
        random.shuffle(deck)
        self._deck = deck
        self._cards_done = 0
        if not deck:
            hb.card_progress.value = ""
            hb.card_question.value = "Нет карточек для выбранной области."
            hb.btn_reveal.visible = False
            hb.card_answer_box.visible = False
            hb.card_actions.visible = False
            self.main.page.update()
            return
        self._show_card()

    def _show_card(self):
        hb = self.main.view.handbook_tab
        if not self._deck:
            hb.card_progress.value = f"Готово! Отмечено изученными: {self._cards_done}."
            hb.card_question.value = "🎉 Все карточки пройдены."
            hb.btn_reveal.visible = False
            hb.card_answer_box.visible = False
            hb.card_actions.visible = False
            self._render_progress()
            self.main.page.update()
            return
        hb.card_progress.value = (
            f"Знаю: {self._cards_done}   ·   Осталось: {len(self._deck)}"
        )
        hb.card_question.value = self._deck[0]["question"]
        hb.btn_reveal.visible = True
        hb.card_answer_box.visible = False
        hb.card_actions.visible = False
        self.main.page.update()

    def handle_cards_reveal(self, e):
        if not self._deck:
            return
        card = self._deck[0]
        hb = self.main.view.handbook_tab
        hb.card_answer.value = (
            card["answer"]
            if self._is_overlay(card["source"])
            else html_to_markdown(card["answer"])
        )
        hb.btn_reveal.visible = False
        hb.card_answer_box.visible = True
        hb.card_actions.visible = True
        self.main.page.update()

    def handle_cards_know(self, e):
        if not self._deck:
            return
        card = self._deck.pop(0)
        if not self.handbook.is_studied(card["question"]):
            self.handbook.toggle_studied(card["question"])
        self._cards_done += 1
        self._show_card()

    def handle_cards_repeat(self, e):
        if not self._deck:
            return
        self._deck.append(self._deck.pop(0))
        self._show_card()

    def handle_quiz_check(self, e):
        if not self._current_topic:
            return
            
        hb = self.main.view.handbook_tab
        user_answer = hb.quiz_input.value
        
        if not user_answer or not user_answer.strip():
            self.main._show_error("Пожалуйста, введите ваш ответ.")
            return

        hb.quiz_btn_check.disabled = True
        hb.quiz_progress.visible = True
        hb.quiz_result.controls.clear()
        self.main.page.update()

        question = self._current_topic.get("question", "")
        reference_answer = self._current_topic.get("answer", "")
        
        def job():
            try:
                result = self.main.analyzer.evaluate_quiz_answer(
                    question=question,
                    reference_answer=reference_answer,
                    user_answer=user_answer
                )
            except Exception as ex:
                logging.error(f"Ошибка при оценке ответа: {ex}")
                result = {"evaluation": "Error", "feedback": f"Произошла ошибка: {ex}"}
            
            self._render_quiz_result(result)
        
        self.main._run_bg(job)
        
    def _render_quiz_result(self, result: dict):
        hb = self.main.view.handbook_tab
        hb.quiz_btn_check.disabled = False
        hb.quiz_progress.visible = False

        evaluation = result.get("evaluation", "Error")
        feedback = result.get("feedback", "Произошла ошибка.")
        color_map = {
            "Correct": ft.Colors.GREEN_600,
            "Partially Correct": ft.Colors.ORANGE_600,
            "Incorrect": ft.Colors.RED_600,
            "Error": ft.Colors.RED_600,
        }
        icon_map = {
            "Correct": ft.Icons.CHECK_CIRCLE,
            "Partially Correct": ft.Icons.INFO,
            "Incorrect": ft.Icons.CANCEL,
            "Error": ft.Icons.ERROR,
        }

        hb.quiz_result.controls = [
            ft.Chip(
                label=ft.Text(evaluation, weight=ft.FontWeight.BOLD),
                bgcolor=color_map.get(evaluation),
                leading=ft.Icon(icon_map.get(evaluation)),
            ),
            ft.Container(
                ft.Column(
                    [
                        ft.Text("Комментарий ИИ:", weight=ft.FontWeight.BOLD),
                        ft.Markdown(
                            feedback,
                            extension_set="gitweball",
                            code_theme="atom-one-dark",
                        ),
                    ]
                ),
                padding=15,
                shape=ft.RoundedRectangleBorder(radius=8),
                border=ft.border.Border.all(1, ft.Colors.OUTLINE_VARIANT),
            ),
            ft.ExpansionPanelList(
                controls=[
                    ft.ExpansionPanel(
                        header=ft.ListTile(title=ft.Text("Показать эталонный ответ")),
                        content=ft.Container(
                            ft.Markdown(
                                html_to_markdown(self._current_topic.get("answer", "")),
                                extension_set="gitweball",
                                code_theme="atom-one-dark",
                            ),
                            padding=15,
                        ),
                    )
                ]
            ),
            ft.Divider(),
            ft.Row(
                [
                    ft.Text("Отметить тему как изученную?"),
                    ft.IconButton(
                        icon=ft.Icons.CHECK_CIRCLE,
                        icon_color=ft.Colors.GREEN,
                        tooltip="Знаю",
                        on_click=lambda e: self._quiz_toggle_studied_status(True),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.REFRESH,
                        icon_color=ft.Colors.ORANGE,
                        tooltip="Повторить",
                        on_click=lambda e: self._quiz_toggle_studied_status(False),
                    ),
                ],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]
        self.main.page.update()

    def _quiz_toggle_studied_status(self, studied: bool):
        if not self._current_topic:
            return
            
        question = self._current_topic.get("question")
        is_currently_studied = self.handbook.is_studied(question)
        if is_currently_studied != studied:
            self.handbook.toggle_studied(question)
            
        self.main._show_info(
            "Статус обновлён", 
            f"Тема отмечена как {'изученная' if studied else 'требующая повторения'}."
        )
        self._render_handbook(self.main.view.handbook_tab.search_field.value)
        self.main.page.update()
