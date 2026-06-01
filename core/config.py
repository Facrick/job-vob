import json
import logging
from pathlib import Path
from typing import Any


class AppConfig:
    """Компонент централизованного управления конфигурациями и тайм-аутами приложения"""

    def __init__(self, config_path: str = "data/settings.json"):
        self.config_path = Path(config_path)
        self.defaults = {
            "llm_model": "llama-3.3-70b-versatile",
            "llm_temperature_generation": 0.15,
            "llm_temperature_adjustment": 0.3,
            "browser_timeout_ms": 40000,
            "human_mouse_steps_min": 10,
            "human_mouse_steps_max": 25,
            "base_delay_ms_min": 1500,
            "base_delay_ms_max": 3000,
            "default_salary": 160000,
            "max_vacancies_per_search": 50,
        }
        self.settings: dict = {}
        self.load_config()

    def load_config(self) -> None:
        """Загрузка конфигурации из файла с созданием дефолтной при отсутствии"""
        try:
            if self.config_path.exists():
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.settings = json.load(f)
                logging.info(f"[Config] Настройки успешно загружены из {self.config_path}")
            else:
                self.settings = self.defaults.copy()
                self.config_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(self.settings, f, indent=4, ensure_ascii=False)
                logging.info(f"[Config] Создан дефолтный файл настроек: {self.config_path}")
        except json.JSONDecodeError as e:
            logging.error(f"[Config] Ошибка парсинга JSON: {e}, откат на дефолты")
            self.settings = self.defaults.copy()
        except Exception as e:
            logging.error(f"[Config] Сбой обработки конфигурации, откат на дефолты: {e}")
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


class PromptRepository:
    """Класс изоляции системных инструкций и эталонных примеров для ИИ"""

    @staticmethod
    def get_cover_letter_instruction() -> str:
        return (
            "ROLE & CONTEXT:\n"
            "Ты — прагматичный Senior QA Automation Engineer и строгий ИТ-редактор. "
            "Твоя цель — составить сильное, емкое и сугубо техническое сопроводительное письмо от лица соискателя.\n\n"
            "КРИТИЧЕСКИЕ ТРЕБОВАНИЯ К ОПОРЕ НА РЕЗЮМЕ:\n"
            "1. Текст письма должен ИСКЛЮЧИТЕЛЬНО основываться на реальном стеке технологий, опыте работы и фактах из предоставленного ниже ТЕКСТА РЕЗЮМЕ кандидата.\n"
            "2. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО выдумывать инструменты, языки программирования, фреймворки или библиотеки, которых нет в тексте резюме кандидата.\n"
            "3. Найди реальные пересечения между требованиями вакансии и текстом резюме. Покажи решение 2-3 ключевых болей вакансии через подтвержденный опыт соискателя.\n"
            "4. Объем письма — строго до 3 абзацев (до 800 символов). Пиши сухо, как инженер инженеру, без маркетинговой воды.\n\n"
            "ФОРМАТ ОТВЕТА: Выдай строго JSON-объект с ключами 'letter' (строка с текстом письма) и 'recommendations' (список тем/технологий из вакансии, которых НЕТ в резюме кандидата)."
        )

    @staticmethod
    def get_adjustment_instruction() -> str:
        return "Верни JSON с ключом 'letter': обновленный текст письма."

    @staticmethod
    def get_mock_interview_system_prompt(vacancy_title: str, handbook_topics: list) -> str:
        topics_str = ", ".join(handbook_topics[:10])
        return (
            f"Ты — строгий Senior QA Lead. Проводи техническое собеседование на позицию '{vacancy_title}'.\n\n"
            f"Темы для вопросов: {topics_str}\n\n"
            "Правила:\n"
            "- Задавай по одному вопросу за раз\n"
            "- После ответа кандидата давай краткую обратную связь\n"
            "- В конце каждого ответа спрашивай 'Готовы продолжить?'\n"
            "- Оценивай глубину понимания, а не заучивание\n"
        )
