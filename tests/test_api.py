"""Тесты API-клиента hh.ru и оркестратора SearchService — офлайн (без сети/Playwright)."""
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


# ── SearchService: фолбэк ─────────────────────────────────────
class _FakeApi:
    def __init__(self, result=None, exc=None):
        self.result, self.exc, self.called = result, exc, False

    def search(self, **kw):
        self.called = True
        if self.exc:
            raise self.exc
        return self.result


class _FakeParser:
    def __init__(self, result):
        self.result, self.called = result, False

    def parse_market(self, **kw):
        self.called = True
        return self.result


def _service(use_api, api, parser):
    svc = SearchService(config=FakeConfig(use_official_api=use_api))
    svc._make_api = lambda: api
    svc._make_parser = lambda: parser
    return svc


_KW = dict(text="QA", period=7, area=113, experience="between1And3", schedule="remote")


def test_uses_api_when_ok():
    api, parser = _FakeApi(result=[{"id": "1"}]), _FakeParser([{"id": "X"}])
    res = _service(True, api, parser).search(**_KW)
    assert res == [{"id": "1"}]
    assert api.called and not parser.called


def test_falls_back_on_error():
    api, parser = _FakeApi(exc=RuntimeError("network")), _FakeParser([{"id": "P"}])
    res = _service(True, api, parser).search(**_KW)
    assert res == [{"id": "P"}]
    assert api.called and parser.called


def test_falls_back_on_empty():
    api, parser = _FakeApi(result=[]), _FakeParser([{"id": "P"}])
    res = _service(True, api, parser).search(**_KW)
    assert res == [{"id": "P"}]
    assert parser.called


def test_api_disabled_uses_parser():
    api, parser = _FakeApi(result=[{"id": "1"}]), _FakeParser([{"id": "P"}])
    res = _service(False, api, parser).search(**_KW)
    assert res == [{"id": "P"}]
    assert not api.called and parser.called
