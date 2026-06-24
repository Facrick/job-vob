"""Вкладка «Аналитика»: зарплатный график, хитмап навыков, журнал событий."""
import logging
import statistics
from datetime import datetime

from nicegui import run, ui

from core.skill_heatmap import extract_top_skills
from gui_ng.theme import STATUS_STYLE


class _AnalyticsMixin:
    """Методы аналитики: зарплатная статистика, хитмап навыков, журнал событий."""

    def draw_analytics_chart(self):
        vacancies = self.repo.get_vacancies_filtered("all")
        mins, maxs, midpoints = [], [], []
        for v in vacancies:
            # int(): зарплаты из БД могут быть float — иначе range()/// ниже падают
            lo = int(v.get("salary_min") or 0)
            hi = int(v.get("salary_max") or 0)
            if lo or hi:
                mid = (lo + hi) // 2 if lo and hi else (lo or hi)
                midpoints.append(mid)
                if lo: mins.append(lo)
                if hi: maxs.append(hi)

        box = self.el["salary_box"]
        box.clear()
        with box:
            if not midpoints:
                ui.label(
                    "Зарплата не указана ни в одной вакансии из базы. "
                    "hh.ru часто скрывает зарплату — это нормально."
                ).classes("italic vob-muted text-sm")
                return

            median_val = int(statistics.median(midpoints))
            mean_val   = int(sum(midpoints) / len(midpoints))
            min_val    = min(mins) if mins else 0
            max_val    = max(maxs) if maxs else 0
            with_salary = len(midpoints)
            total       = len(vacancies)

            # Пояснение к данным
            ui.label(
                f"Данные по {with_salary} из {total} вакансий, у которых указана зарплата."
            ).classes("text-xs vob-muted")
            ui.separator()

            # Компактный формат сумм: 93 000 → «93k», 300 000 → «300k».
            # Длинные числа («300 000 ₽», 26px) не влезали в плашку и ломались
            # на 3 строки — короткая запись и читается лучше, и помещается.
            def fmt_k(n: int) -> str:
                if n >= 1_000_000:
                    return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M ₽"
                if n >= 1_000:
                    return f"{n // 1000}k ₽"
                return f"{n} ₽"

            # KPI-плашки зарплат (единый стиль .vob-kpi, гамма темы)
            stats = [
                ("Медиана", median_val, "#a78bfa", "show_chart",
                 "Половина вакансий предлагает больше, половина — меньше этой суммы. "
                 "Лучший ориентир для переговоров."),
                ("Среднее", mean_val, "#c084fc", "functions",
                 "Среднее арифметическое. Может быть завышено из-за редких вакансий с очень высокой зарплатой."),
                ("Минимум", min_val, "#60a5fa", "south",
                 "Минимальная зарплата «от» среди всех вакансий с указанной вилкой."),
                ("Максимум", max_val, "#fb7a3c", "north",
                 "Максимальная зарплата «до» среди всех вакансий с указанной вилкой."),
            ]
            with ui.row().classes("gap-2 flex-wrap w-full"):
                for label, value, color, icon, tip in stats:
                    if value == 0:
                        continue
                    tip_text = f"{tip}  ({value:,} ₽)".replace(",", " ")
                    kpi = ui.element("div").classes("vob-kpi").style(
                        f"--vob-accent:{color}"
                    ).props(f'title="{tip_text}"')
                    with kpi:
                        with ui.element("div").classes("vob-kpi-icon"):
                            ui.icon(icon)
                        with ui.element("div").classes("vob-kpi-text"):
                            ui.label(label).classes("vob-kpi-label")
                            ui.label(fmt_k(value)).classes("vob-kpi-value").style(
                                "font-size:20px"
                            )

            ui.separator()

            # Гистограмма с динамическими бакетами — делим реальный диапазон на 5 частей
            lo_bound = min(midpoints)
            hi_bound = max(midpoints)
            step = max(1, (hi_bound - lo_bound) // 5)

            # Округляем шаг до красивых чисел
            for rnd in [100_000, 50_000, 25_000, 10_000, 5_000, 1_000]:
                if step >= rnd:
                    step = ((step + rnd - 1) // rnd) * rnd
                    break

            edges = list(range(
                (lo_bound // step) * step,
                ((hi_bound // step) + 2) * step,
                step,
            ))
            if len(edges) < 2:
                edges = [lo_bound, hi_bound + 1]

            def fmt(n): return f"{n:,}".replace(",", " ")

            buckets = []
            for i in range(len(edges) - 1):
                a, b = edges[i], edges[i + 1]
                lbl = f"{fmt(a)} – {fmt(b)} ₽"
                cnt = sum(1 for s in midpoints if a <= s < b)
                buckets.append((lbl, cnt))

            max_cnt = max((c for _, c in buckets), default=0) or 1
            ui.label("Распределение вакансий по зарплате:").classes("text-xs vob-muted")
            for lbl, cnt in buckets:
                if cnt == 0:
                    continue
                pct = max(2, cnt / max_cnt * 100)
                with ui.row().classes("items-center gap-2 w-full no-wrap"):
                    ui.label(lbl).classes("text-sm").style("flex:0 0 44%")
                    with ui.element("div").classes("flex-grow").style(
                        "background:#ffffff14;border-radius:4px;height:20px;min-width:0"
                    ):
                        # Фирменный градиент оранж→фиолет (Aurora)
                        ui.element("div").classes("vob-grad-bar-h").style(
                            f"height:20px;border-radius:4px;width:{pct:.1f}%"
                        )
                    ui.label(f"{cnt} вак.").classes("text-xs vob-muted").style("flex:0 0 50px;text-align:right")

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

            # Извлекаем навыки из резюме для сравнения
            resume_text = self._safe_resume_text().lower()
            has_resume = bool(resume_text.strip())

            total_vac = len(vacancies)
            max_count = skills[0]["count"]

            # Легенда — приглушённая, в тон общему стилю (без кричащих цветов)
            with ui.row().classes("gap-3 items-center flex-wrap"):
                ui.label(f"По {total_vac} вакансиям в базе.").classes("text-xs vob-muted")
                if has_resume:
                    ui.element("div").style(
                        "width:10px;height:10px;border-radius:99px;"
                        "background:linear-gradient(135deg,#fb7a3c,#a78bfa);flex-shrink:0"
                    )
                    ui.label("есть в резюме").classes("text-xs vob-muted")
                    ui.element("div").style(
                        "width:10px;height:10px;border-radius:99px;"
                        "background:#3f3f46;flex-shrink:0"
                    )
                    ui.label("нет в резюме").classes("text-xs vob-muted")
            ui.separator()

            for item in skills:
                skill_name = item["skill"]
                count = item["count"]
                pct_of_market = count / total_vac * 100
                ratio = count / max_count

                # Проверяем есть ли навык в резюме
                in_resume = has_resume and skill_name.lower() in resume_text

                # «в резюме» → фирменный фиолет-акцент (приглушённо),
                # «нет в резюме» → нейтрально-серый: это не ошибка, не алертим красным.
                badge_style = (
                    "background:rgba(167,139,250,.12);color:#c4b5fd;"
                    "border:1px solid rgba(167,139,250,.35)"
                    if in_resume else
                    "background:rgba(255,255,255,.04);color:#71717a;"
                    "border:1px solid #2a2a36"
                )
                badge_text = "✓ в резюме" if in_resume else "нет в резюме"

                with ui.column().classes("w-full gap-0"):
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label(skill_name).classes("text-sm truncate").style(
                            "flex:1 1 0;min-width:0"
                        )
                        if has_resume:
                            # label+div, а не ui.badge: тема форсит .q-badge
                            # color:#fff !important — наш приглушённый цвет перебивался.
                            ui.label(badge_text).style(
                                f"{badge_style};font-size:10px;font-weight:600;"
                                "padding:2px 8px;border-radius:6px;line-height:1.3;"
                                "white-space:nowrap;flex:0 0 auto"
                            )
                        ui.label(f"{count} вак.").classes("text-xs vob-muted").style(
                            "flex:0 0 52px;text-align:right"
                        )
                        ui.label(f"{pct_of_market:.0f}%").classes("text-xs font-bold").style(
                            "flex:0 0 36px;text-align:right;color:#a78bfa"
                        ).props(f'title="Требуется в {pct_of_market:.1f}% вакансий из базы"')
                    with ui.element("div").style(
                        "background:#ffffff0a;border-radius:99px;height:6px;width:100%;margin-bottom:6px"
                    ):
                        # «в резюме» → фирменный градиент (навык подсвечен),
                        # «нет в резюме» → приглушённый серый, не отвлекает.
                        fill = (
                            "linear-gradient(90deg,#fb7a3c,#a78bfa)"
                            if (in_resume or not has_resume) else
                            "#3f3f46"
                        )
                        ui.element("div").style(
                            f"height:6px;border-radius:99px;background:{fill};"
                            f"width:{max(2, ratio * 100):.1f}%;transition:width .3s"
                        )

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

            with ui.column().classes("w-full gap-0"):
                for row in rows:
                    date_str = row["date"]
                    total    = row["total"]
                    applied  = row.get("applied") or 0
                    interview = row.get("interview") or 0
                    offer    = row.get("offer") or 0

                    ratio = total / max_total
                    # Жёсткая сетка: дата | бар | число | бейджи — колонки
                    # выровнены по всем строкам, ничего не «плавает».
                    with ui.element("div").style(
                        "display:grid;align-items:center;width:100%;"
                        "grid-template-columns:84px 1fr 28px 96px;"
                        "column-gap:12px;padding:3px 0"
                    ):
                        ui.label(date_str).classes("text-xs vob-muted").style(
                            "font-family:monospace;white-space:nowrap"
                        )
                        with ui.element("div").style(
                            "background:#ffffff0a;border-radius:99px;height:10px;"
                            "width:100%;min-width:0;overflow:hidden"
                        ):
                            ui.element("div").style(
                                f"height:10px;border-radius:99px;"
                                f"background:linear-gradient(90deg,#fb7a3c,#a78bfa);"
                                f"width:{max(3, ratio * 100):.1f}%;transition:width .35s"
                            )
                        ui.label(str(total)).classes("text-sm font-bold").style(
                            "color:#e4e4e7;text-align:right;font-variant-numeric:tabular-nums"
                        )
                        # Зона бейджей — фиксированная, выровнена по правому краю
                        with ui.row().classes("no-wrap gap-1 justify-end items-center").style(
                            "min-width:0"
                        ):
                            for cnt, sym, skey, tip in (
                                (applied,   "↑", "applied",   "Откликов"),
                                (interview, "✔", "interview", "Собеседований"),
                                (offer,     "★", "offer",     "Офферов"),
                            ):
                                if not cnt:
                                    continue
                                col = STATUS_STYLE[skey][1]
                                ui.label(f"{sym}{cnt}").style(
                                    f"background:{col}1f;color:{col};"
                                    f"border:1px solid {col}40;font-size:10px;"
                                    "font-weight:600;padding:1px 6px;border-radius:6px;"
                                    "line-height:1.4;white-space:nowrap;flex:0 0 auto"
                                ).props(f'title="{tip}: {cnt}"')

    # ── Статистика зарплат соискателей ───────────────────────────────────

    def _salary_query(self) -> str:
        """Возвращает текстовое значение роли из combo_salary_role."""
        val = self.el["combo_salary_role"].value
        if isinstance(val, dict):
            # NiceGUI с with_input=True может вернуть {'value': idx, 'label': '...'}
            label = val.get("label", "")
            return label.lower().strip() if label else ""
        if val is None:
            return ""
        return str(val).lower().strip()

    async def handle_collect_salary_stats(self):
        """Запускает сбор зарплатных ожиданий соискателей по выбранной роли."""
        query = self._salary_query()
        if not query:
            ui.notify("Выберите роль для сбора статистики", type="warning")
            return

        self._salary_collect_cancelled = False

        btn = self.el["btn_collect_salary"]
        btn_stop = self.el["btn_stop_salary"]
        btn.props("loading disabled")
        btn_stop.set_visibility(True)
        box = self.el["salary_box"]
        box.clear()
        with box:
            _init_lbl = ui.label("Проверяем авторизацию на hh.ru…").classes("italic vob-muted text-sm")

        try:
            from core.scraper import HHParser
            from playwright.sync_api import sync_playwright
            parser = HHParser()

            # Резюме hh.ru отдаёт только залогиненным — берём статус из общего
            # кэша (тот же, что в CRM), без лишнего запуска браузера.
            is_authed = await self.get_hh_auth()
            if not is_authed:
                ui.notify("Нужна авторизация — открываем браузер", type="info")
                _init_lbl.set_text("Войдите в аккаунт hh.ru в открывшемся окне…")
                def _do_login():
                    with sync_playwright() as p:
                        return parser._login_in_browser(p)
                logged_in = await run.io_bound(_do_login)
                if not logged_in:
                    ui.notify("Авторизация не выполнена — сбор отменён", type="negative")
                    _init_lbl.set_text("Авторизуйтесь на hh.ru и повторите сбор.")
                    return
                # Ручной вход прошёл — обновляем общий кэш и badge в CRM.
                self._mark_hh_authed()
                self._set_hh_auth_ui(True)

            box.clear()
            with box:
                ui.label("Собираем данные с hh.ru, подождите…").classes("italic vob-muted text-sm")
                prog = ui.linear_progress(value=0).classes("w-full")
                status_lbl = ui.label("").classes("text-xs vob-muted")

            def _progress(msg: str, pct: int):
                prog.set_value(pct / 100)
                status_lbl.set_text(msg)

            max_pages = int(self.config.get("salary_max_pages") or 5)
            concurrency = int(self.config.get("salary_concurrency") or 3)
            stats = await run.io_bound(
                parser.collect_salary_stats,
                query,
                max_pages=max_pages,
                concurrency=concurrency,
                progress_callback=_progress,
                should_cancel=lambda: self._salary_collect_cancelled,
            )
            if self._salary_collect_cancelled:
                ui.notify("Сбор остановлен", type="warning")
                if stats.get("count", 0) > 0:
                    self.repo.save_salary_stats(query, stats)
                    self.draw_salary_stats(stats)
                else:
                    box.clear()
                    with box:
                        ui.label("Сбор остановлен.").classes("italic vob-muted text-sm")
            else:
                logging.debug(f"[salary] saving stats query={query!r} count={stats.get('count')}")
                self.repo.save_salary_stats(query, stats)
                self.draw_salary_stats(stats)
                ui.notify(
                    f"Собрано {stats['count']} резюме по запросу «{query}»",
                    type="positive",
                )
        except Exception as ex:
            import traceback
            logging.error(f"[salary_stats] Ошибка сбора: {ex}\n{traceback.format_exc()}")
            ui.notify(f"Ошибка сбора: {ex}", type="negative", multi_line=True)
            box.clear()
            with box:
                ui.label(f"Ошибка: {ex}").classes("text-sm text-negative")
        finally:
            btn.props(remove="loading disabled")
            btn_stop.set_visibility(False)

    def handle_stop_salary_collect(self):
        self._salary_collect_cancelled = True
        ui.notify("Останавливаем сбор…", type="info")

    def draw_salary_stats(self, stats: dict | None = None):
        """Отрисовывает статистику зарплат соискателей.

        Если stats не передан — берёт из БД по текущей выбранной роли.
        """
        if stats is None:
            query = self._salary_query()
            if query:
                stats = self.repo.get_salary_stats(query)

        box = self.el["salary_box"]
        box.clear()
        logging.debug(f"[salary] draw_salary_stats count={stats.get('count') if stats else None} median={stats.get('median') if stats else None}")
        with box:
            if not stats or stats.get("count", 0) == 0:
                ui.label(
                    "Нет данных. Выберите роль и нажмите «Собрать»."
                ).classes("italic vob-muted text-sm")
                return

            collected_at = stats.get("collected_at", "")
            if collected_at:
                try:
                    dt = datetime.fromisoformat(collected_at)
                    age = (datetime.now() - dt).days
                    age_str = f"сегодня" if age == 0 else f"{age} дн. назад"
                    ui.label(
                        f"По {stats['count']} резюме · собрано {age_str}"
                    ).classes("text-xs vob-muted")
                except Exception:
                    ui.label(f"По {stats['count']} резюме").classes("text-xs vob-muted")
            else:
                ui.label(f"По {stats['count']} резюме").classes("text-xs vob-muted")
            ui.separator()

            def fmt_k(n: int) -> str:
                if n >= 1_000_000:
                    return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M ₽"
                if n >= 1_000:
                    return f"{n // 1000}k ₽"
                return f"{n} ₽"

            kpi_items = [
                ("Медиана", stats["median"], "#a78bfa", "show_chart"),
                ("Среднее", stats["mean"],   "#c084fc", "functions"),
                ("Минимум", stats["min"],    "#60a5fa", "south"),
                ("Максимум", stats["max"],   "#fb7a3c", "north"),
            ]
            with ui.row().classes("gap-2 flex-wrap w-full"):
                for label, value, color, icon in kpi_items:
                    if not value:
                        continue
                    kpi = ui.element("div").classes("vob-kpi").style(
                        f"--vob-accent:{color}"
                    ).props(f'title="{label}: {value:,} ₽"'.replace(",", " "))
                    with kpi:
                        with ui.element("div").classes("vob-kpi-icon"):
                            ui.icon(icon)
                        with ui.element("div").classes("vob-kpi-text"):
                            ui.label(label).classes("vob-kpi-label")
                            ui.label(fmt_k(value)).classes("vob-kpi-value").style(
                                "font-size:20px"
                            )

            distribution = stats.get("distribution", [])
            if distribution:
                ui.separator()
                ui.label("Распределение ожиданий соискателей:").classes("text-xs vob-muted")
                max_cnt = max(b["count"] for b in distribution) or 1

                def fmt_k(n: int) -> str:
                    return f"{n // 1000}к" if n % 1000 == 0 else f"{n:,}".replace(",", " ")

                for bucket in distribution:
                    cnt = bucket["count"]
                    pct = max(2, cnt / max_cnt * 100)
                    lbl = f"{fmt_k(bucket['from'])} – {fmt_k(bucket['to'])} ₽"
                    with ui.row().classes("items-center gap-2 w-full no-wrap"):
                        ui.label(lbl).classes("text-sm").style("flex:0 0 44%")
                        with ui.element("div").classes("flex-grow").style(
                            "background:#ffffff14;border-radius:4px;height:20px;min-width:0"
                        ):
                            ui.element("div").classes("vob-grad-bar-h").style(
                                f"height:20px;border-radius:4px;width:{pct:.1f}%"
                            )
                        ui.label(f"{cnt} рез.").classes("text-xs vob-muted").style(
                            "flex:0 0 50px;text-align:right"
                        )

    def handle_salary_role_change(self, value=None):
        """При смене роли в выпадашке — подгружаем сохранённый снимок если есть."""
        # e.args приходит как {'value': 0, 'label': 'QA Engineer'} или список
        if isinstance(value, list):
            value = value[0] if value else None
        if isinstance(value, dict):
            label = value.get("label", "")
            value = label.lower().strip() if label else None
        query = str(value).lower().strip() if value is not None else self._salary_query()
        logging.debug(f"[salary] role_change query={query!r}")
        if not query:
            box = self.el["salary_box"]
            box.clear()
            with box:
                ui.label(
                    "Выберите роль и нажмите «Собрать» — "
                    "приложение просканирует резюме соискателей на hh.ru."
                ).classes("italic vob-muted text-sm")
            return
        stats = self.repo.get_salary_stats(str(query))
        logging.debug(f"[salary] got stats from db: {bool(stats)}, count={stats.get('count') if stats else 0}")
        self.draw_salary_stats(stats)

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
