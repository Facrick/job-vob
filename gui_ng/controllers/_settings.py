"""Миксин вкладки Настройки."""


class _SettingsMixin:
    """Методы вкладки Настройки: синхронизация UI-состояния настроек."""

    def _resume_display_name(self) -> str:
        """Возвращает имя резюме для отображения: оригинальное если есть, иначе имя файла."""
        original = self.config.get("resume_original_name")
        if original:
            return original
        path = self.resume.file_path
        return path.name if path.exists() else ""

    def _refresh_settings_ui(self) -> None:
        """Обновляет элементы вкладки Настройки из текущего состояния."""
        # Метка резюме на вкладке Настройки
        if "resume_label_s" in self.el:
            name = self._resume_display_name()
            self.el["resume_label_s"].set_text(
                f"📄 {name}" if name else "Файл не загружен"
            )
        # Значения select-ов моделей (могли измениться извне)
        if "select_llm_model" in self.el:
            self.el["select_llm_model"].set_value(self.config.get("llm_model"))
        if "select_llm_analysis_model" in self.el:
            self.el["select_llm_analysis_model"].set_value(
                self.config.get("llm_analysis_model")
            )
        if "input_max_vacancies" in self.el:
            self.el["input_max_vacancies"].set_value(
                self.config.get("max_vacancies_per_search")
            )
        if "input_concurrency" in self.el:
            self.el["input_concurrency"].set_value(
                self.config.get("search_concurrency")
            )
        if "input_salary_pages" in self.el:
            self.el["input_salary_pages"].set_value(
                self.config.get("salary_max_pages") or 5
            )
        if "input_salary_concurrency" in self.el:
            self.el["input_salary_concurrency"].set_value(
                self.config.get("salary_concurrency") or 3
            )
