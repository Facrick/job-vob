import json
import logging
from pathlib import Path
from typing import Any


class AppConfig:
    """Централизованные настройки и тайм-ауты приложения.

    Реализован как синглтон (по пути файла): раньше AppConfig() создавался
    в LetterAnalyzer, ResumeEntity и HHParser независимо — каждый читал и
    мог перезаписывать settings.json. Теперь один экземпляр на путь.
    """

    _instances: dict = {}

    def __new__(cls, config_path: str | None = None):
        from core.paths import user_path

        key = str(config_path) if config_path else str(user_path("data/settings.json"))
        instance = cls._instances.get(key)
        if instance is None:
            instance = super().__new__(cls)
            cls._instances[key] = instance
        return instance

    def __init__(self, config_path: str | None = None):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        from core.paths import user_path

        self.config_path = (
            Path(config_path) if config_path else user_path("data/settings.json")
        )
        self.defaults = {
            "llm_model": "llama-3.3-70b-versatile",
            "llm_fallback_model": "llama-3.1-8b-instant",
            "llm_analysis_model": "llama-3.1-8b-instant",  # анализ вакансии — быстрая модель
            "llm_temperature_generation": 0.15,
            "llm_temperature_adjustment": 0.3,
            "use_official_api": True,  # основной источник — api.hh.ru (фолбэк: парсер)
            "browser_headless": True,  # анализ вакансий без видимого окна Chrome
            "browser_timeout_ms": 40000,
            "human_mouse_steps_min": 10,
            "human_mouse_steps_max": 25,
            "base_delay_ms_min": 1500,
            "base_delay_ms_max": 3000,
            "max_vacancies_per_search": 50,
            "salary_expectation": 0,
        }
        self.settings: dict = {}
        self.load_config()

    def load_config(self) -> None:
        """Загрузка конфигурации из файла с созданием дефолтной при отсутствии"""
        try:
            if self.config_path.exists():
                with open(self.config_path, encoding="utf-8") as f:
                    self.settings = json.load(f)
                logging.info(
                    f"[Config] Настройки успешно загружены из {self.config_path}"
                )
            else:
                self.settings = self.defaults.copy()
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=4, ensure_ascii=False)
                logging.info(
                    f"[Config] Создан дефолтный файл настроек: {self.config_path}"
                )
        except json.JSONDecodeError as e:
            logging.error(f"[Config] Ошибка парсинга JSON: {e}, откат на дефолты")
            self.settings = self.defaults.copy()
        except Exception as e:
            logging.error(
                f"[Config] Сбой обработки конфигурации, откат на дефолты: {e}"
            )
            self.settings = self.defaults.copy()

    def get(self, key: str) -> Any:
        """Получение значения настройки"""
        return self.settings.get(key, self.defaults.get(key))

    def set(self, key: str, value: Any) -> None:
        """Установка значения настройки и сохранение в файл"""
        self.settings[key] = value
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            logging.error(f"[Config] Не удалось сохранить настройку {key}: {e}")
