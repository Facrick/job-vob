class BasePage:
    def __init__(self, page):
        self.page = page

    def open(self, url):
        self.page.goto(url)
        self.page.wait_for_selector(".vob-rail")

    def is_visible(self, selector):
        return self.page.is_visible(selector)
    
    def inner_text(self, selector):
        self.page.wait_for_selector(selector)
        return self.page.inner_text(selector)
    
    def wait_for_selector(self, selector):
        self.page.wait_for_selector(selector)
    
    def click(self, selector):
        self.page.click(selector)