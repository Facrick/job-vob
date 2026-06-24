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
    # ── Отказ ──────────────────────────────────────────────────────────────────
    ("вам отказали",             VacancyStatus.REJECTED),   # точная фраза кнопки hh.ru
    ("отказ",                    VacancyStatus.REJECTED),
    ("отклонен",                 VacancyStatus.REJECTED),
    ("не подош",                 VacancyStatus.REJECTED),   # "не подошел/ёл/ли"
    # ── Оффер ──────────────────────────────────────────────────────────────────
    ("вам предложили работу",    VacancyStatus.OFFER),      # точная фраза кнопки hh.ru
    ("предложение о работе",     VacancyStatus.OFFER),
    ("job offer",                VacancyStatus.OFFER),
    # «оффер» убран — слово встречается в описаниях вакансий («после — оффер»)
    # ── Собеседование ──────────────────────────────────────────────────────────
    ("приглашение на интервью",  VacancyStatus.INTERVIEW),
    ("вас пригласили",           VacancyStatus.INTERVIEW),
    ("приглашён",                VacancyStatus.INTERVIEW),  # ё-версия
    ("телефонное интервью",      VacancyStatus.INTERVIEW),
    # ── Отклик отправлен / на рассмотрении ─────────────────────────────────────
    ("вы откликнулись",          VacancyStatus.APPLIED),    # точная фраза кнопки hh.ru
    ("вы уже откликнулись",      VacancyStatus.APPLIED),
    ("ваш отклик",               VacancyStatus.APPLIED),
    ("отклик рассматривается",   VacancyStatus.APPLIED),
    ("отклик просмотрен",        VacancyStatus.APPLIED),
    ("отклик отправлен",         VacancyStatus.APPLIED),
    ("просмотрен работодателем", VacancyStatus.APPLIED),
    ("response sent",            VacancyStatus.APPLIED),
    # ── Кнопка «Откликнуться» → вакансия открыта, отклика нет ──────────────────
    ("можно откликнуться",       VacancyStatus.DISCOVERED),
]


def map_hh_status(hh_status_text: str) -> VacancyStatus | None:
    """Маппит текст статуса hh.ru на наш VacancyStatus.

    Возвращает None, если не удалось распознать.
    """
    text = (hh_status_text or "").lower()
    for keyword, status in _HH_KEYWORDS:
        if keyword in text:
            return status
    return None


# Ранг этапов воронки. Синхронизация обновляет статус ТОЛЬКО если новый этап
# ВЫШЕ текущего по рангу. Понижение пропускаем (страница hh.ru ненадёжно
# отражает отклик, ложная «Новая» не должна затирать реальные «Отклик/Интервью»).
# Оффер и отказ — наверху ранга, поэтому решения работодателя всё равно проставляются.
_STATUS_RANK: dict[str, int] = {
    VacancyStatus.DISCOVERED.value: 0,
    VacancyStatus.PROCESSED.value:  1,
    VacancyStatus.APPLIED.value:    2,
    VacancyStatus.INTERVIEW.value:  3,
    VacancyStatus.OFFER.value:      4,
    VacancyStatus.REJECTED.value:   5,
}


class SyncResult:
    """Итог одной синхронизации."""

    def __init__(self):
        self.updated:      list[dict] = []   # {vacancy_id, title, company, old, new}
        self.skipped_same: int = 0            # статус уже актуален
        self.skipped_back: int = 0            # hh.ru показал более ранний этап — не откатываем
        self.not_in_crm:   int = 0            # вакансия есть на hh.ru но не в CRM
        self.unrecognized: list[str] = []     # тексты статусов, которые не распознали

    @property
    def total_negotiations(self) -> int:
        return (len(self.updated) + self.skipped_same + self.skipped_back +
                self.not_in_crm + len(self.unrecognized))

    def summary_lines(self) -> list[str]:
        lines = [f"Переговоров на hh.ru: {self.total_negotiations}"]
        if self.updated:
            lines.append(f"Обновлено статусов: {len(self.updated)}")
        if self.skipped_same:
            lines.append(f"Уже актуальны: {self.skipped_same}")
        if self.skipped_back:
            lines.append(f"Пропущено (этап не выше текущего): {self.skipped_back}")
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

        # Закрытая/архивная вакансия — это НЕ статус отклика. Закрытие вакансии
        # не меняет твой этап в воронке, поэтому просто пропускаем (и НЕ пишем
        # в «нераспознанные» — это не ошибка парсинга).
        if hh_text == "закрыта":
            result.skipped_same += 1
            continue

        new_status = map_hh_status(hh_text)
        if new_status is None:
            if hh_text:
                result.unrecognized.append(hh_text)
                logging.warning(
                    f"[Sync] {title} ({vid}): нераспознанный статус hh.ru «{hh_text}»"
                )
            else:
                logging.info(
                    f"[Sync] {title} ({vid}): статус не определён (пустая строка) — пропуск"
                )
            continue

        vacancy = repo.get_vacancy_by_id(vid)
        if vacancy is None:
            # Вакансия есть на hh.ru но не в CRM — добавляем с минимальными данными
            # и сразу проставляем статус из hh.ru.
            repo.save_vacancies([{
                "id": vid,
                "title": title,
                "company": company,
                "status": str(new_status),
            }])
            logging.info(
                f"[Sync] {title} ({vid}): добавлена в CRM со статусом «{new_status}»"
            )
            result.updated.append({
                "vacancy_id": vid,
                "title": title,
                "company": company,
                "old": "—",
                "new": str(new_status),
            })
            continue

        current = str(vacancy.get("status") or VacancyStatus.DISCOVERED.value)
        new_str = str(new_status)

        if current == new_str:
            result.skipped_same += 1
            continue

        # Обновляем ТОЛЬКО если новый этап ВЫШЕ текущего по рангу.
        # Оффер и отказ стоят наверху ранга, поэтому проставляются поверх
        # любого предыдущего этапа; «Новая»/«Отклик» не понижают «Интервью».
        if _STATUS_RANK.get(new_str, 0) <= _STATUS_RANK.get(current, 0):
            result.skipped_back += 1
            logging.info(
                f"[Sync] {title} ({vid}): пропуск — hh.ru даёт «{new_str}» (ранг {_STATUS_RANK.get(new_str,0)}), "
                f"CRM уже «{current}» (ранг {_STATUS_RANK.get(current,0)})"
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
