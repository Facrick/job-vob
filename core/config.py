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
        self.config_path = Path(config_path) if config_path else user_path("data/settings.json")
        self.defaults = {
            "llm_model": "llama-3.3-70b-versatile",
            "llm_fallback_model": "llama-3.1-8b-instant",
            "llm_analysis_model": "llama-3.1-8b-instant",  # анализ вакансии — быстрая модель
            "llm_temperature_generation": 0.15,
            "llm_temperature_adjustment": 0.3,
            "use_official_api": True,   # основной источник — api.hh.ru (фолбэк: парсер)
            "browser_headless": True,   # анализ вакансий без видимого окна Chrome
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
    def get_vacancy_analysis_instruction() -> str:
        return (
            "Ты — Senior QA Engineer и карьерный аналитик. Проанализируй вакансию "
            "и (если есть) резюме кандидата. Будь конкретным и техническим, без воды.\n\n"
            "Верни СТРОГО JSON-объект со следующими ключами:\n"
            "{\n"
            '  "summary": "1-2 предложения: суть роли и грейд",\n'
            '  "key_requirements": ["3-6 главных требований вакансии"],\n'
            '  "stack": ["ключевые технологии и инструменты из вакансии"],\n'
            '  "match": "2-3 предложения: насколько резюме соответствует вакансии",\n'
            '  "highlights": ["на чём кандидату сделать акцент в отклике"],\n'
            '  "gaps": ["КОРОТКИЕ названия навыков/технологий (1-3 слова), которых '
            "не хватает кандидату\"]\n"
            "}\n"
            "ВАЖНО про gaps: это список КОНКРЕТНЫХ навыков/инструментов одним-двумя "
            "словами (например: \"Docker\", \"Kafka\", \"REST Assured\", "
            "\"Нагрузочное тестирование\"), а НЕ предложения и НЕ общие фразы вроде "
            "\"углубить знания\". Каждый пункт — отдельный навык.\n"
            "Если резюме не предоставлено — в match/highlights/gaps опирайся только "
            "на вакансию и пиши общие рекомендации. Никогда не выдумывай факты о кандидате."
        )

    @staticmethod
    def get_handbook_article_instruction() -> str:
        return (
            "Ты — Senior QA/AQA инженер и автор учебных материалов. Напиши краткую, "
            "но содержательную статью-раздел учебника по заданной теме на русском языке.\n\n"
            "Формат ответа — СТРОГО JSON с двумя ключами:\n"
            "{\n"
            '  "question": "Короткое название темы (заголовок раздела)",\n'
            '  "answer": "Текст статьи в Markdown"\n'
            "}\n\n"
            "Требования к полю answer (Markdown):\n"
            "- используй ### для подзаголовков, списки через -, **жирный** для акцентов, "
            "`инлайн-код` и блоки кода в тройных бэктиках ```;\n"
            "- 3–6 смысловых блоков: что это, зачем, ключевые моменты, пример;\n"
            "- по делу, без воды, с практическим уклоном для подготовки к собеседованию."
        )

    @staticmethod
    def get_handbook_revise_instruction() -> str:
        return (
            "Ты — редактор учебных материалов по QA/AQA. Тебе дают текущий текст "
            "раздела (Markdown) и пожелания по правкам. Верни ТОЛЬКО исправленный "
            "текст раздела в Markdown — без пояснений, преамбул и обрамляющих кавычек. "
            "Сохраняй формат Markdown (###, списки -, `код`, блоки ```)."
        )
