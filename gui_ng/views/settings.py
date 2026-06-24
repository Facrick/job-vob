"""Вкладка Настройки — hh.ru, поиск, данные."""
from contextlib import contextmanager

from nicegui import ui


@contextmanager
def _section(title: str, icon: str, accent: str = "#a78bfa"):
    with ui.element("div").classes("vob-settings-section"):
        with ui.element("div").classes("vob-settings-section-head"):
            with ui.element("div").classes("vob-sec-icon").style(f"--vob-accent:{accent}"):
                ui.icon(icon)
            ui.label(title).classes("vob-settings-section-title")
        with ui.element("div").classes("vob-settings-body"):
            yield



def build_settings_tab(c):
    el = c.el

    with ui.element("div").classes("vob-settings-root"):
        with ui.element("div").classes("vob-settings-scroll"):

            # ── hh.ru ─────────────────────────────────────────────────────
            with _section("Интеграция hh.ru", "work", "#60a5fa"):
                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Статус авторизации").classes("vob-settings-label")
                        ui.label("Учётная запись hh.ru для поиска и откликов").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["hh_auth_badge_s"] = ui.label("⬤  проверка…").classes("vob-auth-badge")
                        el["btn_hh_login_s"] = ui.button(
                            "Войти в hh.ru", icon="login", on_click=c.handle_hh_login
                        ).props("no-caps flat").classes(
                            "vob-btn-accent vob-settings-action-btn"
                        )
                        ui.button(icon="refresh", on_click=c.recheck_hh_auth).props(
                            "flat round dense"
                        ).tooltip("Перепроверить авторизацию")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Авто-синхронизация").classes("vob-settings-label")
                        ui.label("Обновлять статусы откликов автоматически раз в час").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["toggle_autosync"] = ui.switch(
                            "", on_change=c.handle_autosync_toggle
                        ).tooltip("Авто-синхронизация раз в час")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Синхронизация вручную").classes("vob-settings-label")
                        ui.label("Запустить проверку статусов всех вакансий прямо сейчас").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        ui.button(
                            "Синхронизировать", icon="sync", on_click=c.handle_hh_sync
                        ).props("outline no-caps").classes("vob-settings-action-btn")

            # ── Поиск вакансий ────────────────────────────────────────────
            with _section("Поиск вакансий", "travel_explore", "#a78bfa"):
                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Показывать браузер").classes("vob-settings-label")
                        ui.label("Открывать окно Chromium во время парсинга hh.ru").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["toggle_visible_browser"] = ui.switch(
                            "", value=True
                        ).tooltip("Показывать браузер во время поиска")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Максимум вакансий за поиск").classes("vob-settings-label")
                        ui.label("Ограничение числа загружаемых карточек").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["input_max_vacancies"] = ui.select(
                            {25: "25", 50: "50", 100: "100", 200: "200"},
                            value=c.config.get("max_vacancies_per_search") or 50,
                            on_change=lambda e: c.config.set("max_vacancies_per_search", e.value),
                        ).props("dense outlined").style("min-width:100px")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Параллельные вкладки").classes("vob-settings-label")
                        ui.label("Сколько карточек разбирать одновременно (больше = быстрее, но риск капчи)").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["input_concurrency"] = ui.select(
                            {2: "2", 4: "4", 6: "6", 8: "8", 10: "10"},
                            value=c.config.get("search_concurrency") or 6,
                            on_change=lambda e: c.config.set("search_concurrency", e.value),
                        ).props("dense outlined").style("min-width:100px")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Страниц для сбора зарплат").classes("vob-settings-label")
                        ui.label("Максимум страниц резюме на hh.ru (20 резюме/стр)").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["input_salary_pages"] = ui.select(
                            {3: "3 (60 рез.)", 5: "5 (100 рез.)", 10: "10 (200 рез.)",
                             20: "20 (400 рез.)", 50: "50 (1000 рез.)"},
                            value=c.config.get("salary_max_pages") or 5,
                            on_change=lambda e: c.config.set("salary_max_pages", e.value),
                        ).props("dense outlined").style("min-width:140px")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Параллельные вкладки (зарплаты)").classes("vob-settings-label")
                        ui.label("Сколько страниц резюме открывать одновременно (больше = быстрее, но риск капчи)").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["input_salary_concurrency"] = ui.select(
                            {2: "2", 3: "3", 5: "5", 8: "8"},
                            value=c.config.get("salary_concurrency") or 3,
                            on_change=lambda e: c.config.set("salary_concurrency", e.value),
                        ).props("dense outlined").style("min-width:100px")

            # ── Данные ────────────────────────────────────────────────────
            with _section("Данные", "storage", "#fb7a3c"):
                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Резюме").classes("vob-settings-label")
                        el["resume_label_s"] = ui.label("Не загружено").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        ui.button(
                            "Загрузить резюме", icon="upload_file", on_click=c.handle_resume_upload
                        ).props("outline no-caps").classes("vob-settings-action-btn")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Экспорт вакансий").classes("vob-settings-label")
                        ui.label("Сохранить все вакансии из CRM в CSV-файл").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        ui.button(
                            "Экспорт в CSV", icon="download", on_click=c.handle_export
                        ).props("outline no-caps").classes("vob-settings-action-btn")

            # ── ИИ-модели ─────────────────────────────────────────────────
            with _section("ИИ-модели", "psychology", "#c084fc"):
                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Основная модель").classes("vob-settings-label")
                        ui.label("Генерация сопроводительных писем и сложные задачи").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["select_llm_model"] = ui.select(
                            {
                                "meta-llama/llama-3.3-70b-instruct": "Llama 3.3 70B",
                                "meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B",
                                "mistralai/mixtral-8x7b-instruct":   "Mixtral 8x7B",
                                "google/gemma-3-27b-it":              "Gemma 3 27B",
                            },
                            value=c.config.get("llm_model"),
                            on_change=lambda e: c.config.set("llm_model", e.value),
                        ).props("dense outlined").style("min-width:190px")

                with ui.element("div").classes("vob-settings-row"):
                    with ui.element("div").classes("vob-settings-label-group"):
                        ui.label("Быстрая модель").classes("vob-settings-label")
                        ui.label("Анализ вакансий и мелкие правки — скорость важнее качества").classes("vob-settings-hint")
                    with ui.element("div").classes("vob-settings-control"):
                        el["select_llm_analysis_model"] = ui.select(
                            {
                                "meta-llama/llama-3.1-8b-instruct":  "Llama 3.1 8B",
                                "meta-llama/llama-3.2-3b-instruct":  "Llama 3.2 3B",
                                "google/gemma-3-12b-it":              "Gemma 3 12B",
                                "mistralai/mistral-7b-instruct":      "Mistral 7B",
                            },
                            value=c.config.get("llm_analysis_model"),
                            on_change=lambda e: c.config.set("llm_analysis_model", e.value),
                        ).props("dense outlined").style("min-width:190px")
