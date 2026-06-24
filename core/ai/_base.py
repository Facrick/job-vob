"""BaseAIClient — общая инициализация и запрос к LLM (Groq/OpenRouter) с ретраями."""
import json
import logging
import os
import re
import time

from core.config import AppConfig
from core.groq_client import make_groq_client


class BaseAIClient:
    """Базовый класс для AI-движков: выбор провайдера, ретраи, фолбэк на резервную модель."""

    def __init__(self, log_prefix: str = "[AI]"):
        self._log_prefix = log_prefix
        self.config = AppConfig()
        openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        groq_key = (os.getenv("GROQ_API_KEY") or "").strip()
        self.api_key = openrouter_key or groq_key
        if not self.api_key:
            raise ValueError("Не найден API-ключ: задайте OPENROUTER_API_KEY или GROQ_API_KEY в .env")
        self._use_openrouter = bool(openrouter_key)
        self.client = make_groq_client(self.api_key)
        self.model = self.config.get("llm_model")
        self.fallback_model = self.config.get("llm_fallback_model")
        self.analysis_model = self.config.get("llm_analysis_model")
        logging.info(f"{self._log_prefix} Модель: {self.model} (резерв: {self.fallback_model})")

    def _complete(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        *,
        json_mode: bool = True,
        max_tokens: int | None = None,
        max_retries: int = 3,
        model: str | None = None,
    ) -> str:
        """Запрос к LLM с ретраями и фолбэком на резервную модель."""
        if model:
            models = [model]
        else:
            models = [self.model]
            if self.fallback_model and self.fallback_model != self.model:
                models.append(self.fallback_model)

        last_error: Exception | None = None
        for model_name in models:
            for attempt in range(max_retries):
                try:
                    kwargs = dict(
                        messages=messages,
                        model=model_name,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=60,
                    )
                    # OpenRouter: response_format поддерживается не всеми моделями,
                    # передаём только для Groq.
                    if json_mode and not self._use_openrouter:
                        kwargs["response_format"] = {"type": "json_object"}
                    completion = self.client.chat.completions.create(**kwargs)
                    content = completion.choices[0].message.content
                    if not content or not content.strip():
                        raise RuntimeError("Модель вернула пустой ответ")
                    return content
                except Exception as e:
                    last_error = e
                    logging.warning(
                        f"{self._log_prefix} {model_name}: попытка {attempt + 1}/{max_retries} не удалась: {e}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(2**attempt)
            if len(models) > 1:
                logging.warning(
                    f"{self._log_prefix} Переключаюсь на резервную модель после сбоя {model_name}"
                )

        raise last_error if last_error else RuntimeError("AI: неизвестная ошибка")

    @staticmethod
    def _strip_markdown_fence(content: str) -> str:
        """Снимает ```json ... ``` обёртку, которую модель иногда добавляет вокруг JSON."""
        text = content.strip()
        match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        return match.group(1) if match else text

    @staticmethod
    def _quote_bare_array_words(content: str) -> str:
        """Оборачивает в кавычки «голые» слова в JSON-массивах (частая ошибка модели).

        Пример брака: ["Docker", ELK, "Kafka", SDLC] → ["Docker", "ELK", "Kafka", "SDLC"]
        """
        return re.sub(r'([,\[]\s*)([A-Za-zА-Яа-яЁё][\w.+-]*)(\s*[,\]])', r'\1"\2"\3', content)

    def _parse_json_safe(self, content: str, fallback: dict | None = None) -> dict:
        """Парсит JSON-ответ модели, чиня типичный брак (markdown-обёртку, bare-слова)."""
        cleaned = self._strip_markdown_fence(content)
        try:
            return json.loads(cleaned)
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            return json.loads(self._quote_bare_array_words(cleaned))
        except (json.JSONDecodeError, TypeError) as e:
            logging.error(f"{self._log_prefix} Не удалось распарсить JSON-ответ: {e}. Ответ: {content}")
            return dict(fallback) if fallback else {}
