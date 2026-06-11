"""Вкладка «Аналитика»: зарплатный график, хитмап навыков, очистка логов."""
import statistics

from nicegui import ui

from core.skill_heatmap import extract_top_skills
from gui_ng.theme import GRADE_HEX


class _AnalyticsMixin:
    """Методы аналитики: зарплатная статистика, хитмап навыков, журнал событий."""

    def draw_analytics_chart(self):
        vacancies = self.repo.get_vacancies_filtered("all")
        # Для каждой вакансии берём среднее между min и max (или одно из них)
        midpoints = []
        mins, maxs = [], []
        for v in vacancies:
            lo = v.get("salary_min") or 0
            hi = v.get("salary_max") or 0
            if lo or hi:
                mid = (lo + hi) // 2 if lo and hi else (lo or hi)
                midpoints.append(mid)
                if lo: mins.append(lo)
                if hi: maxs.append(hi)
        if not midpoints:
            self._show_info("Нет данных", "В базе нет вакансий с указанными зарплатами.")
            return
        box = self.el["salary_box"]
        box.clear()
        with box:
            with ui.row().classes("gap-3 flex-wrap"):
                stats = [
                    ("Минимум", min(mins) if mins else 0, "#64b5f6"),
                    ("Медиана", int(statistics.median(midpoints)), "#7986cb"),
                    ("Среднее", int(sum(midpoints) / len(midpoints)), "#ba68c8"),
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
            counts = [(lbl, sum(1 for s in midpoints if lo <= s < hi)) for lbl, lo, hi in buckets]
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

    def draw_timeline(self):
        """Рисует timeline активности: добавлено вакансий по дням за последние 30 дней."""
        period = int(self.el["combo_timeline_period"].value or 30)
        rows = self.repo.get_activity_by_date(days=period)
        box = self.el["timeline_box"]
        box.clear()
        with box:
            if not rows:
                ui.label(
                    "Нет данных. Вакансии, добавленные до этого обновления, "
                    "не имеют метки даты. Новые вакансии будут отображаться здесь."
                ).classes("italic vob-muted text-sm")
                return

            max_total = max((r["total"] for r in rows), default=0) or 1

            with ui.column().classes("w-full gap-1"):
                for row in rows:
                    date_str = row["date"]
                    total    = row["total"]
                    applied  = row.get("applied") or 0
                    interview = row.get("interview") or 0
                    offer    = row.get("offer") or 0

                    ratio = total / max_total
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label(date_str).classes("text-xs vob-muted").style(
                            "flex:0 0 90px;font-family:monospace"
                        )
                        with ui.element("div").classes("flex-grow").style(
                            "background:#ffffff0d;border-radius:4px;height:18px;min-width:0"
                        ):
                            ui.element("div").style(
                                f"height:18px;border-radius:4px;"
                                f"background:linear-gradient(90deg,#60a5fa,#a78bfa);"
                                f"width:{max(2, ratio * 100):.1f}%"
                            )
                        ui.label(str(total)).classes("text-xs font-bold").style(
                            "color:#e4e4e7;flex:0 0 28px;text-align:right"
                        )
                        # Значки статусов если есть
                        if applied:
                            ui.badge(f"↑{applied}").style(
                                "background:#ff8f0033;color:#ff8f00;"
                                "border:1px solid #ff8f0055;font-size:10px"
                            ).tooltip(f"Откликов: {applied}")
                        if interview:
                            ui.badge(f"✔{interview}").style(
                                "background:#ab47bc33;color:#ab47bc;"
                                "border:1px solid #ab47bc55;font-size:10px"
                            ).tooltip(f"Собеседований: {interview}")
                        if offer:
                            ui.badge(f"★{offer}").style(
                                "background:#66bb6a33;color:#66bb6a;"
                                "border:1px solid #66bb6a55;font-size:10px"
                            ).tooltip(f"Офферов: {offer}")

    def handle_clear_logs(self):
        self.el["logs"].clear()

    def handle_copy_logs(self):
        from nicegui import ui
        children = self.el["logs"].default_slot.children
        content = "\n".join(
            getattr(child, "text", "") for child in children
        )
        if content.strip():
            ui.clipboard.write(content)
            ui.notify("Логи скопированы в буфер обмена", type="positive", icon="content_copy")
        else:
            ui.notify("Лог пустой", type="info")
