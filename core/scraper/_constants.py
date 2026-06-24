"""Общие константы для парсера hh.ru: базовый URL, шаблоны страниц и таймауты Playwright."""

HH_BASE_URL = "https://hh.ru"
HH_VACANCY_URL = HH_BASE_URL + "/vacancy/{vacancy_id}"
HH_LOGIN_URL = HH_BASE_URL + "/account/login"
HH_RESUMES_URL = HH_BASE_URL + "/applicant/resumes"
HH_NEGOTIATIONS_URL = HH_BASE_URL + "/applicant/negotiations"

# Таймауты Playwright в мс — сгруппированы по смыслу ожидания, не по значению.
TIMEOUT_AUTH_MS = 20000  # переход на страницу логина/резюме при проверке сессии
TIMEOUT_PAGE_LOAD_MS = 30000  # обычная загрузка страницы вакансии/поиска
TIMEOUT_PAGE_LOAD_SLOW_MS = 45000  # загрузка страницы под networkidle (тяжёлые SPA-страницы)
TIMEOUT_APPLY_PAGE_MS = 40000  # переход на страницу вакансии перед автоотклика
TIMEOUT_SELECTOR_MS = 10000  # ожидание появления конкретного элемента
TIMEOUT_SELECTOR_SLOW_MS = 20000  # ожидание элемента на медленно рендерящихся страницах
TIMEOUT_SELECTOR_FAST_MS = 8000  # ожидание элемента, который обычно появляется быстро
TIMEOUT_NETWORK_IDLE_MS = 5000  # короткое ожидание затишья в сети
TIMEOUT_SYNC_PAGE_MS = 25000  # переход на вакансию при поштучной синхронизации статусов
