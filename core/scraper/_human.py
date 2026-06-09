"""Эмуляция человеческого поведения + DTO вакансии."""
import random
import logging
from dataclasses import dataclass

from playwright.sync_api import Page

from core.config import AppConfig


@dataclass
class VacancyInfo:
    """DTO для информации о вакансии, полученной парсером."""
    id: str
    title: str
    company: str
    salary_min: int | None
    salary_max: int | None
    description: str
    skills: str
    url: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "company": self.company,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
            "description": self.description,
            "skills": self.skills,
        }


class HumanInteractionEngine:
    """Эмуляция человеческого поведения для обхода антифрода."""

    def __init__(self, config: AppConfig):
        self.config = config

    def move_mouse_randomly(self, page: Page) -> None:
        try:
            for _ in range(random.randint(2, 4)):
                x = random.randint(150, 1000)
                y = random.randint(150, 700)
                steps = random.randint(
                    self.config.get("human_mouse_steps_min"),
                    self.config.get("human_mouse_steps_max"),
                )
                page.mouse.move(x, y, steps=steps)
        except Exception as e:
            logging.debug(f"[Anti-Fraud] Ошибка движения мыши: {e}")

    def apply_adaptive_delay(self, page: Page) -> None:
        delay = random.randint(
            self.config.get("base_delay_ms_min"),
            self.config.get("base_delay_ms_max"),
        )
        page.wait_for_timeout(delay)

    def random_scroll(self, page: Page) -> None:
        try:
            scroll_y = random.randint(200, 800)
            page.evaluate(f"window.scrollBy({{top: {scroll_y}, behavior: 'smooth'}})")
            page.wait_for_timeout(random.randint(500, 1500))
        except Exception as e:
            logging.debug(f"[Anti-Fraud] Ошибка прокрутки: {e}")
