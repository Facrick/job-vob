"""Вкладка «Аналитика»: зарплатный график, хитмап навыков, очистка логов."""
import statistics

from nicegui import ui

from core.skill_heatmap import extract_top_skills
from gui_ng.theme import GRADE_HEX


class _AnalyticsMixin:
    """Методы аналитики: зарплатная статистика, хитмап навыков, журнал событий."""

    def draw_analytics_chart(self):
        vacancies = self.repo.get_vacancies_filtered("all")
        mins = [v["salary_min"] for v in vacancies if v.get("salary_min")]
        maxs = [v["salary_max"] for v in vacancies if v.get("salary_max")]
        if not mins and not maxs:
            self._show_info("Нет данных", "В базе нет вакансий с указанными зарплатами.")
            return
        all_s = mins + maxs
        box = self.el["salary_box"]
        box.clear()
        with box:
            with ui.row().classes("gap-3 flex-wrap"):
                stats = [
                    ("Минимум", min(mins) if mins else 0, "#64b5f6"),
                    ("Медиана", int(statistics.median(all_s)), "#7986cb"),
                    ("Среднее", int(sum(all_s) / len(all_s)), "#ba68c8"),
                    ("Максимум", max(maxs) if maxs else 0, "#81c784"),
                ]
                for label, value, color in stats:
                    with ui.card().style(f"background-color:{color}1a;padding:10px 16px").props("flat"):
                        ui.label(label).classes("text-xs vob-muted")
                        ui.label(f"{value:,} ₽".replace(",", " ")).style(
                            f"font-size:16px;font-weight:700;color:{color}"
                        )
                with ui.card().style("background-color:#7986cb14;padding:10px 16px").props("flat"):
                    ui.label("Вакансий с зарплатой").classes("text-xs vob-muted")
                    ui.label(f"{len(mins)} из {len(vacancies)}").classes("text-base font-bold")
            ui.separator()
            buckets = [
                ("< 80 000", 0, 80_000), ("80 000 – 120 000", 80_000, 120_000),
                ("120 000 – 180 000", 120_000, 180_000),
                ("180 000 – 250 000", 180_000, 250_000),
                ("> 250 000", 250_000, 10_000_000),
            ]
            colors = ["#64b5f6", "#7986cb", "#ba68c8", "#9575cd", "#81c784"]
            counts = [(lbl, sum(1 for s in mins if lo <= s < hi)) for lbl, lo, hi in buckets]
            max_count = max((c for _, c in counts), default=0) or 1
            for (lbl, count), color in zip(counts, colors, strict=False):
                pct = max(2, count / max_count * 100)
                with ui.row().classes("items-center gap-2 w-full no-wrap"):
                    ui.label(lbl).classes("text-sm truncate").style("flex:0 0 38%")
                    with ui.element("div").classes("flex-grow").style(
                        "background:#ffffff14;border-radius:4px;height:20px;min-width:0"
                    ):
                        ui.element("div").style(
                            f"height:20px;border-radius:4px;background-color:{color};width:{pct}%"
                        )
                    ui.label(str(count)).classes("text-xs vob-muted").style("flex:0 0 24px")

    def draw_skill_heatmap(self):
        top_n = int(self.el["combo_heatmap_n"].value or 20)
        vacancies = self.repo.get_vacancies_filtered("all")
        if not vacancies:
            self._show_info("Нет данных", "Соберите вакансии на вкладке CRM.")
            return
        skills = extract_top_skills(vacancies, top_n=top_n, min_count=1)
        box = self.el["heatmap_box"]
        box.clear()
        with box:
            if not skills:
                ui.label(
                    "Навыки не найдены. Убедитесь, что у вакансий заполнено поле «Ключевые навыки»."
                ).classes("italic vob-muted")
                return
            with ui.row().classes("gap-2 items-center flex-wrap"):
                ui.label("Грейды:").classes("text-xs vob-muted")
                for tag, grade in (("J — Junior", "Junior"), ("M — Middle", "Middle"),
                                   ("S — Senior/Lead", "Senior/Lead")):
                    ui.badge(tag).style(
                        f"background-color:{GRADE_HEX[grade]};color:#fff;font-weight:500"
                    )
            ui.separator()
            max_count = skills[0]["count"]
            for item in skills:
                ratio = item["count"] / max_count
                with ui.column().classes("w-full gap-1"):
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label(item["skill"]).classes("text-sm truncate").style(
                            "flex:1 1 0;min-width:0"
                        )
                        for grade in ("Junior", "Middle", "Senior/Lead"):
                            n = item["grades"].get(grade, 0)
                            if not n:
                                continue
                            color = GRADE_HEX[grade]
                            tag = grade[0] if grade != "Senior/Lead" else "S"
                            ui.badge(f"{tag}:{n}").style(
                                f"background-color:{color}33;color:#fff;"
                                f"border:1px solid {color}55;font-weight:600"
                            )
                        ui.badge(str(item["count"])).style(
                            "background-color:#a78bfa33;color:#fff;"
                            "border:1px solid #a78bfa55;font-weight:700"
                        )
                    ui.linear_progress(value=ratio, show_value=False).props("color=primary")

    def handle_clear_logs(self):
        self.el["logs"].clear()
