"""Единая фабрика клиента Groq с поддержкой прокси.

Groq гео-блокирует ряд регионов (включая РФ) и отвечает 403 Forbidden.
Если в .env задан PROXY_URL — пускаем запросы к api.groq.com через него.
Раньше прокси применялся только к парсеру Playwright, а к Groq — нет, из-за
чего AI-функции падали с 403. Обе точки (LetterAnalyzer, MockInterviewEngine)
теперь создают клиент через эту фабрику.
"""
import logging
import os

import httpx
from groq import Groq


def make_groq_client(api_key: str) -> Groq:
    proxy_url = (os.getenv("PROXY_URL") or "").strip()
    if proxy_url:
        http_client = httpx.Client(proxy=proxy_url, timeout=httpx.Timeout(60.0))
        logging.info("[AI] Groq через прокси (PROXY_URL)")
        return Groq(api_key=api_key, http_client=http_client)
    return Groq(api_key=api_key)
