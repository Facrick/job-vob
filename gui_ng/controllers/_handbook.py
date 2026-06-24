"""Вкладка «Учебник»: навигация, просмотр/редактирование, план, упражнения."""
import logging
import re

from nicegui import run, ui

from core.handbook import AI_SECTION
from core.utils import html_to_markdown, normalize_markdown


class _HandbookMixin:
    """Методы вкладки «Учебник» и панели упражнений."""

    def load_handbook(self):
        try:
            self._handbook_sections = self.handbook.get_all_sections()
        except Exception as e:
            logging.error(f"Не удалось загрузить учебник: {e}")
            self._handbook_sections = {}
        self._render_handbook("")

    def _render_progress(self):
        done, total = self.handbook.progress()
        self.el["hb_progress"].set_value((done / total) if total else 0)
        pct = round(done / total * 100) if total else 0
        self.el["hb_progress_label"].set_text(f"Прогресс {pct}% ({done} из {total})")

    def set_handbook_track(self, track: str):
        self.handbook.set_track(track)
        self._current_topic = None
        self._handbook_sections = self.handbook.get_all_sections()
        self._reset_topic_pane()
        self.el["hb_search"].set_value("")
        if self._hb_mode == "plan":
            self._render_learning_plan()
        else:
            self._render_handbook("")
        if self._hb_mode == "exercises":
            self._reset_exercise_pane()

    def _reset_topic_pane(self):
        self.el["hb_topic_title"].set_text("")
        self.el["hb_topic_badge"].set_text("")
        self.el["hb_empty"].set_visibility(True)
        self.el["hb_answer"].set_visibility(False)
        self.el["hb_topic_divider"].set_visibility(False)
        for k in ("hb_btn_edit", "hb_btn_fav", "hb_btn_studied"):
            self.el[k].set_visibility(False)
        self._exit_edit_mode()

    def on_mode_toggle(self, mode: str):
        if self._suppress_mode_change:
            return
        self.set_handbook_mode(mode)

    def set_handbook_mode(self, mode: str):
        self._hb_mode = mode
        self._suppress_mode_change = True
        self.el["hb_mode_toggle"].set_value(mode)
        self._suppress_mode_change = False
        is_plan = mode == "plan"
        is_ex = mode == "exercises"
        self.el["hb_search"].set_visibility(not is_plan)
        self.el["hb_tree"].set_visibility(not is_plan)
        self.el["hb_topic_pane"].set_visibility(not is_plan and not is_ex)
        self.el["hb_plan_box"].set_visibility(is_plan)
        self.el["hb_exercise_box"].set_visibility(is_ex)
        if is_plan:
            self._render_learning_plan()
        else:
            self._render_handbook(self.el["hb_search"].value or "")
        if is_ex:
            self._reset_exercise_pane()

    def handle_handbook_search(self):
        self._render_handbook(self.el["hb_search"].value or "")

    def _render_handbook(self, query: str = ""):
        self._render_progress()
        tree = self.el["hb_tree"]
        tree.clear()
        q = (query or "").strip().lower()
        only_fav = self._hb_mode == "favorites"
        any_shown = False
        with tree:
            for section_name, questions in self._handbook_sections.items():
                sec_match = q in section_name.lower()
                shown = [
                    it for it in questions
                    if (not q or sec_match or q in it.get("question", "").lower())
                    and (not only_fav or self.handbook.is_favorite(it["question"]))
                ]
                if not shown:
                    continue
                any_shown = True
                done, total = self.handbook.section_progress(section_name)
                with ui.expansion(
                    f"{section_name}  ({done}/{total})", value=bool(q) or only_fav
                ).classes("w-full vob-hb-section").props("dense"):
                    for it in shown:
                        self._hb_tile(section_name, it)
            if not any_shown:
                if only_fav:
                    msg = "В избранном пока пусто — отметьте темы ★."
                elif not q and not self._handbook_sections:
                    msg = ("В этом направлении пока нет тем. Введите тему в поиск "
                           "и сгенерируйте раздел ИИ, либо смените направление.")
                else:
                    msg = "Ничего не найдено"
                ui.label(msg).classes("italic vob-muted")
            if q and not only_fav:
                term = query.strip()
                ui.button(
                    f"Сгенерировать раздел «{term}» с помощью ИИ", icon="auto_awesome",
                    on_click=lambda _, t=term: self._generate_handbook_topic(t),
                ).props("flat dense no-caps")

    def _hb_tile(self, section_name: str, item: dict):
        q = item["question"]
        src = item.get("source", "")
        check = "✓ " if self.handbook.is_studied(q) else ""
        star = "★ " if self.handbook.is_favorite(q) else ""
        badge = "🤖 " if src == "ai" else ("✏️ " if src == "user" else "")
        data = {"section": section_name, "question": q, "answer": item["answer"], "source": src}
        lbl = ui.label(check + star + badge + q).classes(
            "cursor-pointer text-sm py-1 px-2 rounded hover:bg-white/5 w-full"
        )
        if check:
            lbl.style("color:#6ee7b7")  # изучено — спокойный мятный (в гамме)
        lbl.on("click", lambda _, d=data: self._on_tile_click(d))

    def _on_tile_click(self, data: dict):
        if self._hb_mode == "exercises":
            self.load_exercise(data)
        else:
            self._show_topic(**data)

    def _compute_learning_plan(self) -> list[tuple[str, int]]:
        resume_raw = self._safe_resume_text().lower()
        resume_words = set(re.findall(r"[a-zа-яё0-9+#./]{2,}", resume_raw))
        counts: dict[str, int] = {}
        for v in self.repo.get_vacancies_filtered("all"):
            for raw in (v.get("skills") or "").split(","):
                skill = raw.strip()
                low = skill.lower()
                if not skill or low in ("не указаны", "не указано", "—", "-"):
                    continue
                skill_words = set(re.findall(r"[a-zа-яё0-9+#./]{2,}", low))
                if skill_words and skill_words.issubset(resume_words):
                    continue
                counts[skill] = counts.get(skill, 0) + 1
        return sorted(counts.items(), key=lambda kv: -kv[1])[:30]

    def _render_learning_plan(self):
        box = self.el.get("hb_plan_list")
        if box is None:
            return
        box.clear()
        plan = self._compute_learning_plan()
        with box:
            if not plan:
                has_vac = bool(self.repo.get_vacancies_filtered("all"))
                hint = ("Соберите вакансии через CRM — план составится из навыков, "
                        "которые работодатели требуют чаще всего." if not has_vac
                        else "Все навыки из ваших вакансий уже есть в резюме — план пуст.")
                ui.label(hint).classes("italic vob-muted text-sm")
                return
            ui.label(
                "Навыки из ваших вакансий, которых нет в резюме (по частоте). "
                "Жмите «в учебник», чтобы открыть материал, или «сгенерировать»."
            ).classes("text-xs vob-muted")
            for skill, count in plan:
                with ui.row().classes("items-center gap-2 w-full no-wrap"):
                    ui.badge(str(count)).style(
                        "background-color:#a78bfa33;color:#fff;"
                        "border:1px solid #a78bfa55;font-weight:700"
                    )
                    ui.label(skill).classes("text-sm truncate").style("flex:1 1 0;min-width:0")
                    topic = self.handbook.find_topic(skill)
                    if topic:
                        section, question, answer, source = topic
                        ui.button(
                            "в учебник", icon="menu_book",
                            on_click=lambda _, s=section, q=question, a=answer, sr=source:
                                self._open_handbook_for(s, q, a, sr),
                        ).props("flat dense no-caps")
                    else:
                        ui.button(
                            "сгенерировать", icon="auto_awesome",
                            on_click=lambda _, t=skill: self._generate_handbook_topic(t),
                        ).props("flat dense no-caps")

    @staticmethod
    def _is_overlay(source: str) -> bool:
        return source in ("ai", "user")

    def _show_topic(self, section: str, question: str, answer: str, source: str = ""):
        self._current_topic = {
            "section": section, "question": question, "answer": answer, "source": source,
        }
        self.el["hb_topic_title"].set_text(question)
        self.el["hb_topic_badge"].set_text({
            "ai": "🤖 сгенерировано ИИ — проверьте", "user": "✏️ изменено",
        }.get(source, ""))
        self.el["hb_empty"].set_visibility(False)
        self.el["hb_topic_divider"].set_visibility(True)
        self.el["hb_answer"].set_visibility(True)
        raw_md = answer if self._is_overlay(source) else html_to_markdown(answer)
        self.el["hb_answer"].set_content(normalize_markdown(raw_md))
        self.el["hb_btn_edit"].set_visibility(True)
        is_fav = self.handbook.is_favorite(question)
        self.el["hb_btn_fav"].set_visibility(True)
        self.el["hb_btn_fav"].props(f'icon={"star" if is_fav else "star_border"}')
        is_studied = self.handbook.is_studied(question)
        self.el["hb_btn_studied"].set_visibility(True)
        self.el["hb_btn_studied"].props(
            f'icon={"check_circle" if is_studied else "check_circle_outline"}'
        )
        self._exit_edit_mode()

    def handle_handbook_favorite(self):
        if not self._current_topic:
            return
        is_fav = self.handbook.toggle_favorite(self._current_topic["question"])
        self.el["hb_btn_fav"].props(f'icon={"star" if is_fav else "star_border"}')
        self._render_handbook(self.el["hb_search"].value or "")

    def handle_handbook_studied(self):
        if not self._current_topic:
            return
        studied = self.handbook.toggle_studied(self._current_topic["question"])
        self.el["hb_btn_studied"].props(
            f'icon={"check_circle" if studied else "check_circle_outline"}'
        )
        self._render_handbook(self.el["hb_search"].value or "")

    def _section_options(self) -> dict[str, str]:
        names = list(self._handbook_sections.keys())
        if AI_SECTION not in names:
            names.append(AI_SECTION)
        return {n: n for n in names}

    def _enter_edit_mode(self):
        t = self._current_topic or {}
        ans, src = t.get("answer", ""), t.get("source", "")
        raw_md = ans if self._is_overlay(src) else html_to_markdown(ans)
        self.el["hb_editor"].set_value(normalize_markdown(raw_md))
        sel = self.el["hb_edit_section"]
        sel.set_options(self._section_options(), value=t.get("section", AI_SECTION))
        sel.set_visibility(True)
        self.el["hb_edit_title"].set_visibility(self._adding_new_topic)
        self.el["hb_view_box"].set_visibility(False)
        self.el["hb_edit_box"].set_visibility(True)
        self.el["hb_btn_edit"].set_visibility(False)

    def _exit_edit_mode(self):
        self._adding_new_topic = False
        self.el["hb_view_box"].set_visibility(True)
        self.el["hb_edit_box"].set_visibility(False)
        self.el["hb_edit_title"].set_visibility(False)
        self.el["hb_edit_section"].set_visibility(False)
        self.el["hb_btn_edit"].set_visibility(bool(self._current_topic))

    def handle_handbook_edit(self):
        if self._current_topic:
            self._adding_new_topic = False
            self._enter_edit_mode()

    def handle_handbook_add_new(self):
        self._adding_new_topic = True
        self._current_topic = None
        self.el["hb_topic_title"].set_text("Новая тема")
        self.el["hb_topic_badge"].set_text("✏️ создаётся")
        self.el["hb_empty"].set_visibility(False)
        self.el["hb_answer"].set_visibility(False)
        self.el["hb_topic_divider"].set_visibility(True)
        for k in ("hb_btn_fav", "hb_btn_studied"):
            self.el[k].set_visibility(False)
        self.el["hb_editor"].set_value("")
        self.el["hb_edit_title"].set_value("")
        sel = self.el["hb_edit_section"]
        sel.set_options(self._section_options(), value=AI_SECTION)
        sel.set_visibility(True)
        self.el["hb_edit_title"].set_visibility(True)
        self.el["hb_view_box"].set_visibility(False)
        self.el["hb_edit_box"].set_visibility(True)
        self.el["hb_btn_edit"].set_visibility(False)

    def handle_handbook_cancel(self):
        self._exit_edit_mode()

    def handle_handbook_save(self):
        new_md = (self.el["hb_editor"].value or "").strip()
        section = (self.el["hb_edit_section"].value or "").strip() or AI_SECTION
        if self._adding_new_topic:
            question = (self.el["hb_edit_title"].value or "").strip()
            if not question:
                self._show_error("Укажите название темы.")
                return
        else:
            if not self._current_topic:
                return
            question = self._current_topic["question"]
        if not new_md:
            self._show_error("Текст материала не может быть пустым.")
            return
        self.handbook.add_or_update_topic(section, question, new_md, ai=False)
        self._handbook_sections = self.handbook.get_all_sections()
        self._adding_new_topic = False
        self._show_topic(section, question, new_md, "user")
        self._render_handbook(self.el["hb_search"].value or "")
        self._show_info("Сохранено", f"Материал «{question}» сохранён в раздел «{section}».")

    async def handle_handbook_ai_fix(self):
        if not self._current_topic:
            return
        current = self.el["hb_editor"].value or ""
        instructions = self.el["hb_instr"].value or ""
        title = self._current_topic.get("question", "")
        self.el["hb_btn_ai_fix"].disable()
        try:
            revised = await run.io_bound(
                self.analyzer.revise_handbook_article, title, current, instructions
            )
            if revised:
                self.el["hb_editor"].set_value(revised)
                self.el["hb_instr"].set_value("")
        except Exception as ex:
            self._show_error(str(ex))
        finally:
            self.el["hb_btn_ai_fix"].enable()

    def _generate_handbook_topic(self, topic: str, context: str = ""):
        ui.timer(0.01, lambda: self._generate_handbook_topic_async(topic, context), once=True)

    async def _generate_handbook_topic_async(self, topic: str, context: str = ""):
        self.el["hb_empty"].set_visibility(False)
        self.el["hb_answer"].set_visibility(True)
        self.el["hb_answer"].set_content(f"⏳ ИИ пишет раздел «{topic}»...")
        self._exit_edit_mode()
        self.switch_to_tab(self.TAB_HANDBOOK)
        try:
            art = await run.io_bound(
                self.analyzer.generate_handbook_article, topic, context, self.handbook.persona
            )
            if not art.get("answer"):
                self._show_error("ИИ не смог сгенерировать материал. Попробуйте ещё раз.")
                return
            self.handbook.add_or_update_topic(AI_SECTION, art["question"], art["answer"], ai=True)
            self._handbook_sections = self.handbook.get_all_sections()
            self.set_handbook_mode("sections")
            self._render_handbook("")
            self._show_topic(AI_SECTION, art["question"], art["answer"], "ai")
            self._show_info(
                "Материал добавлен",
                f"«{art['question']}» сохранён в раздел «{AI_SECTION}». "
                "Отредактируйте при необходимости и нажмите «Сохранить».",
            )
            self._enter_edit_mode()
        except Exception as ex:
            self._show_error(str(ex))

    def _open_handbook_for(self, section: str, question: str, answer: str, source: str):
        self.switch_to_tab(self.TAB_HANDBOOK)
        self.set_handbook_mode("sections")
        self.el["hb_search"].set_value(question)
        self._render_handbook(question)
        self._show_topic(section, question, answer, source)

    # ── упражнения ───────────────────────────────────────────────
    def _reset_exercise_pane(self):
        self._current_exercise = None
        self.el["ex_topic_label"].set_text("Упражнения")
        self.el["ex_empty"].set_visibility(True)
        self.el["ex_content"].set_visibility(False)
        self.el["ex_result"].set_visibility(False)
        self.el["ex_btn_new"].set_visibility(False)
        self.el["ex_spinner"].set_visibility(False)
        self._show_overall_progress()

    def _show_overall_progress(self):
        passed, attempted = self.exercises.stats()
        badge = self.el["ex_progress"]
        if attempted:
            badge.set_text(f"✓ Зачтено: {passed} из {attempted}")
            badge.style(
                "background-color:#a78bfa25;color:#fff;"
                "border:1px solid #a78bfa44"
            )
            badge.set_visibility(True)
        else:
            badge.set_visibility(False)

    def _show_topic_progress(self, question: str):
        prog = self.exercises.get_progress(question)
        badge = self.el["ex_progress"]
        if not prog:
            self._show_overall_progress()
            return
        best = prog.get("best_score", 0)
        attempts = prog.get("attempts", 0)
        color = "#4ade80" if prog.get("passed") else "#fb923c"
        mark = "✓ " if prog.get("passed") else ""
        badge.set_text(f"{mark}Лучший: {best}/100 · попыток: {attempts}")
        badge.style(
            f"background-color:{color}33;color:#fff;"
            f"border:1px solid {color}55;font-weight:600"
        )
        badge.set_visibility(True)

    def load_exercise(self, topic: dict):
        question = topic.get("question", "")
        answer = topic.get("answer", "")
        self.el["ex_topic_label"].set_text(question or "Упражнение")
        self.el["ex_empty"].set_visibility(False)
        self.el["ex_btn_new"].set_visibility(True)
        self.el["ex_result"].set_visibility(False)
        self._show_topic_progress(question)
        bank = self.exercises.get_for_topic(question)
        if bank:
            self._current_exercise = {**bank[-1], "question": question, "answer": answer}
            self._show_exercise()
        else:
            self._generate_exercise(question, answer, save=True)

    def _show_exercise(self):
        ex = self._current_exercise or {}
        self.el["ex_task"].set_content(normalize_markdown(ex.get("task", "")))
        self.el["ex_answer"].set_value("")
        self.el["ex_answer"].props(remove="readonly")
        self.el["ex_result"].set_visibility(False)
        self.el["ex_content"].set_visibility(True)
        self.el["ex_btn_check"].set_visibility(True)

    def handle_exercise_new(self):
        if not self._current_exercise:
            return
        ex = self._current_exercise
        self._generate_exercise(ex.get("question", ""), ex.get("answer", ""), save=True)

    def _generate_exercise(self, question: str, answer: str, save: bool):
        ui.timer(
            0.01,
            lambda: self._generate_exercise_async(question, answer, save),
            once=True,
        )

    async def _generate_exercise_async(self, question: str, answer: str, save: bool):
        self.el["ex_empty"].set_visibility(False)
        self.el["ex_content"].set_visibility(False)
        self.el["ex_spinner"].set_visibility(True)
        try:
            ex = await run.io_bound(
                self.analyzer.generate_validated_exercise,
                question, answer, self.handbook.persona,
            )
        except Exception as ex_err:  # noqa: BLE001
            self._show_error(str(ex_err))
            ex = {}
        finally:
            self.el["ex_spinner"].set_visibility(False)
        if not ex or not ex.get("task"):
            self.el["ex_empty"].set_visibility(True)
            self._show_error("ИИ не смог составить задание. Попробуйте ещё раз.")
            return
        if save:
            self.exercises.add(question, ex)
        self._current_exercise = {**ex, "question": question, "answer": answer}
        self._show_exercise()

    async def handle_exercise_check(self):
        if not self._current_exercise:
            return
        user_answer = (self.el["ex_answer"].value or "").strip()
        if not user_answer:
            self._show_error("Введите решение перед проверкой.")
            return
        ex = self._current_exercise
        self.el["ex_btn_check"].disable()
        self.el["ex_spinner"].set_visibility(True)
        try:
            result = await run.io_bound(
                self.analyzer.grade_exercise,
                ex.get("task", ""), ex.get("reference", ""),
                ex.get("rubric", ""), user_answer,
            )
        except Exception as err:  # noqa: BLE001
            self._show_error(str(err))
            result = None
        finally:
            self.el["ex_spinner"].set_visibility(False)
            self.el["ex_btn_check"].enable()
        if result:
            self._render_exercise_result(result)

    def _render_exercise_result(self, data: dict):
        score = int(data.get("score", 0))
        verdict = data.get("verdict") or (
            "Зачтено" if score >= 70 else "Частично" if score >= 40 else "Не зачтено"
        )
        color = "#4ade80" if score >= 70 else "#fb923c" if score >= 40 else "#f87171"
        badge = self.el["ex_score_badge"]
        badge.set_text(f"{verdict} · {score}/100")
        badge.style(
            f"background-color:{color}33;color:#fff;"
            f"border:1px solid {color}55;font-weight:700"
        )
        parts = []
        correct = data.get("correct") or []
        missing = data.get("missing") or []
        advice = data.get("advice") or ""
        if correct:
            parts.append("**✅ Верно:**\n" + "\n".join(f"- {x}" for x in correct))
        if missing:
            parts.append("**⚠️ Упущено / неверно:**\n" + "\n".join(f"- {x}" for x in missing))
        if advice:
            parts.append(f"**💡 Рекомендация:** {advice}")
        self.el["ex_feedback"].set_content("\n\n".join(parts) or "_Нет деталей._")
        self.el["ex_result"].set_visibility(True)
        question = (self._current_exercise or {}).get("question", "")
        if question:
            self.exercises.record_result(question, score, verdict)
            self._show_topic_progress(question)
