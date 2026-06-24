from pages.base_page import BasePage

class AnalyticsPage(BasePage):
    FUNNEL = "text=Воронка поиска работы"
    TIMELINE_ACTIVE = "text=Timeline активности"
    SALARY = "text=Зарплаты на рынке"
    TOP_SKILLS = "text=Топ навыков рынка"
    REFRESH_BTN = ".vob-btn-refresh"


    def __init__(self, page):
        super().__init__(page)

    def open(self, url):
        super().open(url)
        self.page.click("text=Аналитика")
        self.page.wait_for_selector(self.FUNNEL)

    def refresh_timeline(self):
        self.page.locator(".vob-btn-refresh").nth(0).click()

    def refresh_salary(self):
        self.page.locator(".vob-btn-refresh").nth(1).click()

    def refresh_top_skills(self):
        self.page.locator(".vob-btn-refresh").nth(2).click()



 