"""Фабрика AI-клиента: Groq (с прокси) или OpenRouter (работает в РФ без прокси).

Приоритет выбора провайдера:
  1. OPENROUTER_API_KEY в .env → используем OpenRouter (openai-совместимый клиент)
  2. GROQ_API_KEY + PROXY_URL → Groq через прокси
  3. GROQ_API_KEY → Groq напрямую (может не работать из РФ)

OpenRouter: https://openrouter.ai/ — регистрация без VPN, бесплатный tier есть.
Поддерживает те же модели Llama/Mistral через единый API.
"""
import logging
import os

import httpx


def make_groq_client(api_key: str):
    """Возвращает клиент Groq или OpenRouter в зависимости от .env."""
    openrouter_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if openrouter_key:
        return _make_openrouter_client(openrouter_key)
    return _make_groq_client(api_key)


def _make_groq_client(api_key: str):
    from groq import Groq
    proxy_url = (os.getenv("PROXY_URL") or "").strip()
    if proxy_url:
        http_client = httpx.Client(proxy=proxy_url, timeout=httpx.Timeout(60.0))
        logging.info("[AI] Groq через прокси (PROXY_URL)")
        return Groq(api_key=api_key, http_client=http_client)
    return Groq(api_key=api_key)


def _make_openrouter_client(api_key: str):
    """OpenAI-совместимый клиент для OpenRouter — работает из РФ без прокси."""
    from openai import OpenAI
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        http_client=httpx.Client(timeout=httpx.Timeout(60.0)),
    )
    logging.info("[AI] Провайдер: OpenRouter (OPENROUTER_API_KEY)")
    return client
