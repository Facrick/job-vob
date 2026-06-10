"""Синхронизация статусов вакансий CRM с данными hh.ru.

Логика:
  1. Парсер собирает список переговоров с /applicant/negotiations
  2. Каждый статус hh.ru маппируется на наш VacancyStatus
  3. Статус обновляется только если вакансия есть в CRM И
     новый статус «важнее» текущего (нельзя случайно откатиться назад),
     кроме REJECTED — он обновляется всегда (работодатель отказал).
"""
from __future__ import annotations

import logging

from core.models import VacancyStatus

# ── Маппинг текстов hh.ru → наш статус ──────────────────────────────────────
# Ключи — подстроки (lower), которые ищутся в тексте статуса hh.ru.
# Порядок важен: более специфичные строки — первыми.
_HH_KEYWORDS: list[tuple[str, VacancyStatus]] = [
    # Отказ
    ("отказ",                    VacancyStatus.REJECTED),
    ("отклонен",                 VacancyStatus.REJECTED),
    ("не подош",                 VacancyStatus.REJECTED),   # матчит "не подошел/ёл/ли"
    # Оффер
    ("оффер",                    VacancyStatus.OFFER),
    ("предложение о работе",     VacancyStatus.OFFER),
    ("job offer",                VacancyStatus.OFFER),
    # Собеседование / приглашение — только точные статусные фразы.
    # Одиночные «интервью» / «собеседование» убраны: они встречаются в описаниях
    # вакансий и дают ложные срабатывания для неоткликнутых вакансий.
    # ВАЖНО: «приглашен» убран — это подстрока слова «приглашение».
    ("приглашение на интервью",  VacancyStatus.INTERVIEW),
    ("вас пригласили",           VacancyStatus.INTERVIEW),
    ("приглашён",                VacancyStatus.INTERVIEW),  # ё-версия, не подстрока
    ("телефонное интервью",      VacancyStatus.INTERVIEW),
    # Отклик отправлен / просмотрен — только статусные формулировки
    ("ваш отклик",               VacancyStatus.APPLIED),
    ("вы уже откликнулись",      VacancyStatus.APPLIED),
    ("отклик рассматривается",   VacancyStatus.APPLIED),
    ("отклик просмотрен",        VacancyStatus.APPLIED),
    ("отклик отправлен",         VacancyStatus.APPLIED),
    ("просмотрен работодателем", VacancyStatus.APPLIED),
    ("response sent",            VacancyStatus.APPLIED),
    ("viewed",                   VacancyStatus.APPLIED),
]

# Приоритет: не даунгрейдить статус на «менее важный».
# Исключение: REJECTED всегда перезаписывает (работодатель отказал — факт).
_PRIORITY: dict[str, int] = {
    VacancyStatus.DISCOVERED: 0,
    VacancyStatus.PROCESSED:  1,
    VacancyStatus.APPLIED:    2,
    VacancyStatus.INTERVIEW:  3,
    VacancyStatus.OFFER:      4,
    VacancyStatus.REJECTED:   5,  # финальный статус, высший приоритет
}


def map_hh_status(hh_status_text: str) -> VacancyStatus | None:
    """Маппит текст статуса hh.ru на наш VacancyStatus.

    Возвращает None, если не удалось распознать.
    """
    text = (hh_status_text or "").lower()
    for keyword, status in _HH_KEYWORDS:
        if keyword in text:
            return status
    return None


class SyncResult:
    """Итог одной синхронизации."""

    def __init__(self):
        self.updated:      list[dict] = []   # {vacancy_id, title, company, old, new}
        self.skipped_same: int = 0            # статус уже актуален
        self.skipped_lower: int = 0           # hh.ru даёт менее важный статус
        self.not_in_crm:   int = 0            # вакансия есть на hh.ru но не в CRM
        self.unrecognized: list[str] = []     # тексты статусов, которые не распознали

    @property
    def total_negotiations(self) -> int:
        return (len(self.updated) + self.skipped_same +
                self.skipped_lower + self.not_in_crm + len(self.unrecognized))

    def summary_lines(self) -> list[str]:
        lines = [f"Переговоров на hh.ru: {self.total_negotiations}"]
        if self.updated:
            lines.append(f"Обновлено статусов: {len(self.updated)}")
        if self.skipped_same:
            lines.append(f"Уже актуальны: {self.skipped_same}")
        if self.skipped_lower:
            lines.append(f"Пропущено (hh.ru ниже CRM): {self.skipped_lower}")
        if self.not_in_crm:
            lines.append(f"Нет в CRM (ещё не добавлены): {self.not_in_crm}")
        if self.unrecognized:
            unique = list(dict.fromkeys(self.unrecognized))[:5]
            lines.append(f"Нераспознанные статусы: {', '.join(unique)}")
        return lines


def sync_negotiations(repo, negotiations: list[dict]) -> SyncResult:
    """Обновляет статусы вакансий в CRM по данным negotiations.

    negotiations — список dict от HHParser.fetch_negotiations():
        {vacancy_id, hh_status, title, company}
    """
    result = SyncResult()

    for neg in negotiations:
        vid = str(neg.get("vacancy_id") or "").strip()
        hh_text = str(neg.get("hh_status") or "")
        title   = neg.get("title", vid)
        company = neg.get("company", "")

        new_status = map_hh_status(hh_text)
        if new_status is None:
            if hh_text:
                result.unrecognized.append(hh_text)
            continue

        vacancy = repo.get_vacancy_by_id(vid)
        if vacancy is None:
            result.not_in_crm += 1
            continue

        current = vacancy.get("status") or VacancyStatus.DISCOVERED

        # REJECTED обновляем всегда; иначе — только если новый статус приоритетнее
        current_prio = _PRIORITY.get(str(current), 0)
        new_prio     = _PRIORITY.get(str(new_status), 0)

        if str(current) == str(new_status):
            result.skipped_same += 1
            continue

        if new_status != VacancyStatus.REJECTED and new_prio <= current_prio:
            result.skipped_lower += 1
            logging.debug(
                f"[Sync] {vid} — пропуск: hh.ru «{hh_text}» ({new_status}) "
                f"≤ текущий «{current}»"
            )
            continue

        repo.update_status(vid, new_status)
        logging.info(
            f"[Sync] {title} ({vid}): {current} → {new_status}  (hh.ru: «{hh_text}»)"
        )
        result.updated.append({
            "vacancy_id": vid,
            "title": title,
            "company": company,
            "old": str(current),
            "new": str(new_status),
        })

    return result
