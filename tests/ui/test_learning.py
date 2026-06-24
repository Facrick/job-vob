import allure

@allure.title("Проверка отображения основных графиков раздела 'Аналитика'")
@allure.feature("Аналитика")
def test_analytics_charts(analytics_page):
    assert analytics_page.is_visible(analytics_page.FUNNEL)
    assert analytics_page.is_visible(analytics_page.TIMELINE_ACTIVE)
    assert analytics_page.is_visible(analytics_page.SALARY)
    assert analytics_page.is_visible(analytics_page.TOP_SKILLS)

def test_refresh_timeline(analytics_page):
    analytics_page.refresh_timeline()
    assert analytics_page.is_visible(analytics_page.TIMELINE_ACTIVE)

    
