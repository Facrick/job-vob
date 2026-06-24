"""Тесты API-клиента hh.ru и оркестратора SearchService — офлайн (без сети/Playwright)."""
import asyncio

from core.api_client import HHApiClient
from core.search_service import SearchService
from core.utils import strip_html


class FakeConfig:
    def __init__(self, **vals):
        self.vals = vals

    def get(self, key):
        return self.vals.get(key)


# ── strip_html ────────────────────────────────────────────────
def test_strip_html_basic():
    out = strip_html("<p>Привет</p><ul><li>Python</li><li>SQL</li></ul>")
    assert "Привет" in out
    assert "• Python" in out and "• SQL" in out
    assert "<" not in out          # тегов не осталось


def test_strip_html_entities_and_empty():
    assert strip_html("a &amp; b") == "a & b"
    assert strip_html("") == ""


# ── Маппинг JSON → dict ───────────────────────────────────────
def test_map_salary():
    assert HHApiClient._map_salary({"from": 100000, "to": 150000}) == (100000, 150000)
    assert HHApiClient._map_salary({"from": 90000, "to": None}) == (90000, None)
    assert HHApiClient._map_salary(None) == (None, None)


def test_map_list_item():
    item = {
        "id": 42, "name": "QA Engineer",
        "employer": {"name": "ACME"},
        "salary": {"from": 120000, "to": 180000},
    }
    m = HHApiClient._map_list_item(item)
    assert m["id"] == "42"          # id приводится к строке
    assert m["title"] == "QA Engineer"
    assert m["company"] == "ACME"
    assert (m["salary_min"], m["salary_max"]) == (120000, 180000)


def test_map_detail():
    d = {"description": "<p>Текст</p>", "key_skills": [{"name": "Python"}, {"name": "SQL"}]}
    m = HHApiClient._map_detail(d)
    assert "Текст" in m["description"]
    assert m["skills"] == "Python, SQL"


def test_map_detail_empty():
    m = HHApiClient._map_detail({})
    assert m["skills"] == "Не указаны"
    assert m["description"]


# ── search() офлайн: мокаем сетевой _get_json ─────────────────
def test_search_merges_details():
    client = HHApiClient(config=FakeConfig())

    def fake_get(path, params=None):
        if path == "/vacancies":
            return {"pages": 1, "items": [{
                "id": "1", "name": "QA", "employer": {"name": "ACME"},
                "salary": {"from": 100000, "to": 150000},
            }]}
        if path == "/vacancies/1":
            return {"description": "<p>desc</p>", "key_skills": [{"name": "Python"}]}
        return {}

    client._get_json = fake_get
    res = client.search(text="QA", max_vacancies=10)
    assert len(res) == 1
    assert res[0]["company"] == "ACME"
    assert res[0]["skills"] == "Python"
    assert "desc" in res[0]["description"]


# ── SearchService: поиск идёт через Playwright-парсер ─────────
# Официальный API hh.ru отключён (давал слишком мало вакансий) — единственный
# источник теперь парсер. Тесты проверяют, что SearchService всегда зовёт его.
class _FakeParser:
    def __init__(self, result):
        self.result, self.called, self.kwargs = result, False, None

    async def parse_market_async(self, **kw):
        self.called = True
        self.kwargs = kw
        # Реальный парсер вызывает on_vacancy для каждой вакансии — SearchService
        # фильтрует/дедуплицирует именно в этом колбэке. Воспроизводим это.
        on_vacancy = kw.get("on_vacancy")
        if on_vacancy:
            for v in self.result:
                on_vacancy(v)
        return self.result


class _SyncSearch:
    """Обёртка над SearchService.search, гоняющая async-метод через asyncio.run.

    Позволяет писать обычные (не async) тесты без pytest-asyncio.
    """

    def __init__(self, svc):
        self._svc = svc

    def search(self, **kw):
        return asyncio.run(self._svc.search(**kw))


def _service(parser):
    svc = SearchService(config=FakeConfig())
    svc._make_parser = lambda: parser
    return _SyncSearch(svc)


_KW = dict(text="QA", period=7, area=113, experience="between1And3", schedule="remote")


def test_uses_parser():
    parser = _FakeParser([{"id": "1", "title": "QA Engineer"}])
    res = _service(parser).search(**_KW)
    assert [v["id"] for v in res] == ["1"]
    assert parser.called


def test_passes_should_cancel():
    """should_cancel прокидывается в парсер — иначе кнопка «Стоп» не сработает."""
    parser = _FakeParser([{"id": "1", "title": "QA Engineer"}])
    flag = {"v": False}
    _service(parser).search(**_KW, should_cancel=lambda: flag["v"])
    assert "should_cancel" in parser.kwargs and callable(parser.kwargs["should_cancel"])


def test_expand_dedups_by_id():
    """expand=True по синонимам не должен дублировать вакансии по id."""
    parser = _FakeParser([
        {"id": "1", "title": "QA Engineer"},
        {"id": "1", "title": "QA Engineer"},
        {"id": "2", "title": "QA автотестер"},
    ])
    res = _service(parser).search(**_KW, expand=True)
    assert [v["id"] for v in res] == ["1", "2"]


def test_search_field_defaults_to_full_match():
    """По умолчанию ищем как на hh.ru вручную (заголовок+компания+описание),
    иначе находится в разы меньше вакансий."""
    parser = _FakeParser([{"id": "1", "title": "QA Engineer"}])
    _service(parser).search(text="QA")
    assert parser.kwargs["search_field"] == "name,company_name,description"


def test_headless_passed_through():
    """Переключатель «Показывать браузер» прокидывается в парсер как headless."""
    parser = _FakeParser([{"id": "1", "title": "QA Engineer"}])
    _service(parser).search(text="QA", headless=False)
    assert parser.kwargs["headless"] is False


def test_filters_out_irrelevant_titles():
    """Вакансии, где запрос встретился только в описании (не в названии), отсекаются."""
    parser = _FakeParser([
        {"id": "1", "title": "QA Engineer"},
        {"id": "2", "title": "Курьер (знание Python приветствуется)"},
        {"id": "3", "title": "Инженер по тестированию"},  # синоним QA
    ])
    res = _service(parser).search(text="QA Engineer", expand=True)
    assert sorted(v["id"] for v in res) == ["1", "3"]


def test_irrelevant_title_not_passed_to_on_vacancy():
    """Отсеянная вакансия не должна сохраняться в БД (on_vacancy не вызывается)."""
    parser = _FakeParser([
        {"id": "1", "title": "QA Engineer"},
        {"id": "2", "title": "Бариста"},
    ])
    saved: list[str] = []
    _service(parser).search(text="QA", on_vacancy=lambda v: saved.append(v["id"]))
    assert saved == ["1"]


def test_search_fills_stats():
    """stats-словарь заполняется счётчиками: разобрано / дубли / отсеяно / релевантно."""
    parser = _FakeParser([
        {"id": "1", "title": "QA Engineer"},      # релевантно
        {"id": "1", "title": "QA Engineer"},      # дубль
        {"id": "2", "title": "Бариста"},          # отсеяно по названию
        {"id": "3", "title": "Тестировщик QA"},   # релевантно
    ])
    stats: dict = {}
    _service(parser).search(text="QA", stats=stats)
    assert stats == {
        "parsed": 4, "duplicates": 1, "filtered": 1, "relevant": 2,
    }
