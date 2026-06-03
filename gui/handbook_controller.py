import logging
import random

import flet as ft

from core.handbook import AI_SECTION
from core.utils import html_to_markdown


class HandbookController:

    def __init__(self, main_controller):
        self.main = main_controller
        self.handbook = self.main.handbook

        self._current_topic: dict | None = None
        self._hb_mode: str = "sections"
        self._handbook_sections: dict = {}
        self._quiz_deck: list[dict] = []
        self._quiz_index: int = 0
        self._quiz_score: int = 0
        self._quiz_total: int = 0
        self._current_quiz_question: str = ""
        self._current_quiz_topic: dict = {}

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
            if only_fav:
                msg = "В избранном пока пусто — отметьте темы ★."
            elif not q and not self._handbook_sections:
                # Пустой трек (Backend/Frontend/…): база ещё не наполнена.
                msg = ("В этом направлении пока нет тем. Введите тему в поиск "
                       "и сгенерируйте раздел с помощью ИИ, либо смените направление.")
            else:
                msg = "Ничего не найдено"
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

    def set_handbook_track(self, track: str):
        """Переключает направление учебника (M20): контент, прогресс, избранное."""
        self.handbook.set_track(track)
        self._current_topic = None
        self._quiz_deck = []
        self._handbook_sections = self.handbook.get_all_sections()
        hb = self.main.view.handbook_tab
        # Сбрасываем панель темы и выходим из квиза в обычный режим.
        hb.topic_title.value = ""
        hb.topic_badge.value = ""
        hb.text_handbook.value = "Выберите вопрос в списке слева, чтобы увидеть ответ."
        hb.btn_edit.visible = hb.btn_fav.visible = hb.btn_studied.visible = False
        self._exit_edit_mode()
        if self._hb_mode == "quiz":
            self.set_handbook_mode("sections")
        else:
            self._render_handbook(hb.search_field.value or "")

    def set_handbook_mode(self, mode: str):
        self._hb_mode = mode
        hb = self.main.view.handbook_tab
        hb.set_active_mode(mode)
        hb.mode_bar.update()

        is_quiz = mode == "quiz"

        hb.tree_handbook.visible = not is_quiz
        hb.search_field.visible = not is_quiz
        hb.topic_pane.visible = not is_quiz
        hb.quiz_box.visible = is_quiz

        if is_quiz:
            # Reset answer input when entering quiz
            hb.quiz_answer_input.read_only = False
            self.main.page.update()
        else:
            self._render_handbook(hb.search_field.value)

    def handle_handbook_search(self, e):
        self._render_handbook(e.control.value)

    def _compute_learning_plan(self) -> list[tuple[str, int]]:
        resume_raw = self.main._safe_resume_text().lower()
        # Split resume into words for more accurate matching
        import re
        resume_words = set(re.findall(r"[a-zа-яё0-9+#./]{2,}", resume_raw))

        counts: dict[str, int] = {}
        for v in self.main.repo.get_vacancies_filtered("all"):
            for raw in (v.get("skills") or "").split(","):
                skill = raw.strip()
                low = skill.lower()
                if not skill or low in ("не указаны", "не указано", "—", "-"):
                    continue
                # Check if skill words are ALL in resume (word-level match)
                skill_words = set(re.findall(r"[a-zа-яё0-9+#./]{2,}", low))
                if skill_words and skill_words.issubset(resume_words):
                    continue
                counts[skill] = counts.get(skill, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])[:30]

    def _render_learning_plan(self, tree):
        plan = self._compute_learning_plan()
        if not plan:
            has_vacancies = bool(self.main.repo.get_vacancies_filtered("all"))
            if not has_vacancies:
                hint = "Соберите вакансии через CRM — план составится из навыков, которые работодатели требуют чаще всего."
            else:
                hint = "Все навыки из ваших вакансий уже присутствуют в резюме — план пуст. Соберите новые вакансии."
            tree.controls.append(
                ft.Container(
                    content=ft.Column(spacing=8, controls=[
                        ft.Icon(ft.Icons.CHECKLIST, size=36, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text("📋 План обучения", weight=ft.FontWeight.BOLD, size=14),
                        ft.Text(hint, italic=True, color=ft.Colors.ON_SURFACE_VARIANT, size=13),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.Padding(20, 30, 20, 30),
                    alignment=ft.Alignment(0, 0),
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

    def handle_quiz_start(self, e):
        hb = self.main.view.handbook_tab
        scope = hb.quiz_scope.value

        deck = []
        for section, items in self.handbook.get_all_sections().items():
            for it in items:
                q = it["question"]
                if scope == "favorites" and not self.handbook.is_favorite(q):
                    continue
                deck.append({"section": section, "question": q, "answer": it["answer"], "source": it.get("source", "")})

        random.shuffle(deck)
        deck = deck[:20]  # max 20 questions per session

        if not deck:
            self.main._show_error("Нет вопросов для выбранной области.")
            return

        self._quiz_deck = deck
        self._quiz_index = 0
        self._quiz_score = 0
        self._quiz_total = len(deck)
        self._show_quiz_question()

    def _show_quiz_question(self):
        hb = self.main.view.handbook_tab
        if self._quiz_index >= self._quiz_total:
            # Session done
            pct = round(self._quiz_score / self._quiz_total * 100) if self._quiz_total else 0
            hb.quiz_question_text.value = f"🎉 Квиз завершён! Результат: {self._quiz_score}/{self._quiz_total} ({pct}%)"
            hb.quiz_answer_input.visible = False
            hb.btn_quiz_check.visible = False
            hb.btn_quiz_next.visible = False
            hb.quiz_eval_chip.visible = False
            hb.quiz_feedback_text.visible = False
            hb.quiz_correct_label.visible = False
            hb.quiz_correct_answer.visible = False
            hb.quiz_progress_label.value = "Сессия завершена"
            self.main.page.update()
            return

        topic = self._quiz_deck[self._quiz_index]
        hb.quiz_progress_label.value = f"Вопрос {self._quiz_index + 1} из {self._quiz_total}"
        hb.quiz_question_text.value = "⏳ ИИ формулирует вопрос..."
        hb.quiz_answer_input.value = ""
        hb.quiz_answer_input.visible = False
        hb.btn_quiz_check.visible = False
        hb.btn_quiz_next.visible = False
        hb.quiz_eval_chip.visible = False
        hb.quiz_feedback_text.visible = False
        hb.quiz_correct_label.visible = False
        hb.quiz_correct_answer.visible = False
        hb.quiz_spinner.visible = True
        self.main.page.update()

        def job():
            try:
                question = self.main.analyzer.generate_quiz_question(
                    topic["question"], topic["answer"], persona=self.handbook.persona
                )
            except Exception:
                question = topic["question"]
            hb.quiz_question_text.value = question
            # store generated question for evaluation
            self._current_quiz_question = question
            self._current_quiz_topic = topic
            hb.quiz_answer_input.visible = True
            hb.btn_quiz_check.visible = True
            hb.quiz_spinner.visible = False
            self.main.page.update()

        self.main._run_bg(job)

    def handle_quiz_next(self, e):
        self._quiz_index += 1
        self._show_quiz_question()

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

    def _generate_handbook_topic(self, topic: str, context: str = ""):
        hb = self.main.view.handbook_tab
        hb.text_handbook.value = f"⏳ ИИ пишет раздел «{topic}»..."
        self._exit_edit_mode()
        if self.main.page:
            self.main.page.update()

        def job():
            art = self.main.analyzer.generate_handbook_article(
                topic, context, persona=self.handbook.persona
            )
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

    def handle_quiz_check(self, e):
        hb = self.main.view.handbook_tab
        user_answer = (hb.quiz_answer_input.value or "").strip()
        if not user_answer:
            self.main._show_error("Введите ваш ответ перед проверкой.")
            return

        hb.btn_quiz_check.disabled = True
        hb.quiz_spinner.visible = True
        hb.quiz_eval_chip.visible = False
        hb.quiz_feedback_text.visible = False
        self.main.page.update()

        question = getattr(self, "_current_quiz_question", self._current_quiz_topic.get("question", ""))
        topic = getattr(self, "_current_quiz_topic", self._quiz_deck[self._quiz_index] if self._quiz_deck else {})
        reference = topic.get("answer", "")

        def job():
            result = {"evaluation": "Error", "feedback": "Ошибка при проверке."}
            try:
                result = self.main.analyzer.evaluate_quiz_answer(
                    question=question, reference_answer=reference, user_answer=user_answer
                )
            except Exception as ex:
                result = {"evaluation": "Error", "feedback": str(ex)}

            evaluation = result.get("evaluation", "Error")
            feedback = result.get("feedback", "")

            color_map = {
                "Correct": ft.Colors.GREEN_600,
                "Partially Correct": ft.Colors.ORANGE_600,
                "Incorrect": ft.Colors.RED_600,
                "Error": ft.Colors.RED_600,
            }
            label_map = {
                "Correct": "✅ Верно",
                "Partially Correct": "⚠️ Частично верно",
                "Incorrect": "❌ Неверно",
                "Error": "⚠️ Ошибка",
            }

            if evaluation == "Correct":
                self._quiz_score += 1

            hb.quiz_eval_chip.label = ft.Text(label_map.get(evaluation, evaluation), weight=ft.FontWeight.BOLD)
            hb.quiz_eval_chip.bgcolor = ft.Colors.with_opacity(0.2, color_map.get(evaluation, ft.Colors.GREY))
            hb.quiz_eval_chip.visible = True

            hb.quiz_feedback_text.value = feedback
            hb.quiz_feedback_text.visible = True

            # Show correct answer from handbook
            answer_md = reference if topic.get("source") in ("ai", "user") else html_to_markdown(reference)
            hb.quiz_correct_answer.value = answer_md
            hb.quiz_correct_label.visible = True
            hb.quiz_correct_answer.visible = True

            hb.quiz_answer_input.read_only = True
            hb.btn_quiz_check.visible = False
            hb.btn_quiz_next.visible = True
            hb.quiz_spinner.visible = False
            hb.btn_quiz_check.disabled = False

            hb.quiz_progress_label.value = f"Вопрос {self._quiz_index + 1} из {self._quiz_total}  •  Очков: {self._quiz_score}"
            self.main.page.update()

        self.main._run_bg(job)
