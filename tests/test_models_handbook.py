"""Тесты статусов вакансий и целостности учебника."""
from core.handbook import QAHandbook
from core.models import VacancyStatus


def test_vacancy_status_is_str():
    assert VacancyStatus.DISCOVERED == "discovered"
    assert str(VacancyStatus.OFFER) == "offer"
    assert VacancyStatus.APPLIED.value == "applied"


def test_handbook_loads():
    sections = QAHandbook(track="qa").get_all_sections()
    assert len(sections) >= 13
    # новые разделы присутствуют
    keys = " ".join(sections.keys())
    assert "11." in keys and "12." in keys


def test_handbook_has_transferred_topics():
    sections = QAHandbook(track="qa").get_all_sections()
    questions = [it["question"] for items in sections.values() for it in items]
    blob = " | ".join(questions)
    for tag in ("6.4", "6.6", "6.7", "7.2", "7.4", "12.1", "12.7"):
        assert tag in blob, f"тема {tag} отсутствует в учебнике"


def test_find_topic_maps_gaps_correctly():
    hb = QAHandbook(track="qa")
    # совпадение по слову в вопросе, а не по названию раздела
    assert hb.find_topic("Docker")[1].startswith("4.3")
    assert hb.find_topic("SOLID")[1].startswith("7.4")
    assert hb.find_topic("Stream API")[1].startswith("6.6")
    assert hb.find_topic("исключения")[1].startswith("6.7")
    assert hb.find_topic("CI/CD")[1].startswith("4.2")
    assert hb.find_topic("REST Assured")[1].startswith("5.4")
    assert hb.find_topic("Mockito")[1].startswith("12.7")


def test_find_topic_unknown_returns_none():
    hb = QAHandbook(track="qa")
    assert hb.find_topic("блокчейн криптовалюта") is None
    assert hb.find_topic("") is None


def test_find_topic_synonyms_and_forms():
    """Синонимы и словоформы должны находить тему (рекалл)."""
    hb = QAHandbook(track="qa")
    # зонтичный синоним «автотестирование» → раздел автоматизации
    assert hb.find_topic("Автотестирование")[1].startswith("5")
    assert hb.find_topic("AQA")[1].startswith("5")
    # словоформа
    assert hb.find_topic("коллекции")[1].startswith("6.5")
    assert hb.find_topic("ООП")[1].startswith("7.1")


def test_find_topic_generic_phrases_return_none():
    """Чисто общие фразы (без QA-термина) не должны цеплять тему."""
    hb = QAHandbook(track="qa")
    assert hb.find_topic("опыт работы") is None
    assert hb.find_topic("углубить знания") is None
    assert hb.find_topic("коммуникабельность") is None


def test_overlay_add_persist_and_reload(tmp_path):
    ov = tmp_path / "ov.json"
    hb = QAHandbook(overlay_path=str(ov))
    hb.add_or_update_topic("🤖 ИИ-материалы", "Тема X", "<p>текст</p>", ai=True)
    # видно в merged
    items = [it for sec in hb.get_all_sections().values() for it in sec]
    assert any(it["question"] == "Тема X" for it in items)
    # сохранилось на диск и читается заново
    hb2 = QAHandbook(overlay_path=str(ov))
    found = [it for sec in hb2.get_all_sections().values()
             for it in sec if it["question"] == "Тема X"]
    assert found and found[0]["source"] == "ai" and "текст" in found[0]["answer"]


def test_overlay_update_replaces(tmp_path):
    hb = QAHandbook(overlay_path=str(tmp_path / "ov.json"))
    hb.add_or_update_topic("Раздел", "Q", "<p>v1</p>")
    hb.add_or_update_topic("Раздел", "Q", "<p>v2</p>")
    qs = [it for it in hb.get_all_sections()["Раздел"] if it["question"] == "Q"]
    assert len(qs) == 1 and "v2" in qs[0]["answer"]


def test_overlay_overrides_base(tmp_path):
    hb = QAHandbook(overlay_path=str(tmp_path / "ov.json"))
    sec, items = next(iter(hb._base.items()))
    q = items[0]["question"]
    hb.add_or_update_topic(sec, q, "<p>ПЕРЕОПРЕДЕЛЕНО</p>")
    new = [it for it in hb.get_all_sections()[sec] if it["question"] == q][0]
    assert "ПЕРЕОПРЕДЕЛЕНО" in new["answer"]


def test_favorites_toggle_and_persist(tmp_path):
    prefs = tmp_path / "prefs.json"
    hb = QAHandbook(prefs_path=str(prefs))
    assert hb.is_favorite("Тема") is False
    assert hb.toggle_favorite("Тема") is True
    assert hb.is_favorite("Тема") is True
    # сохранилось и читается заново
    hb2 = QAHandbook(prefs_path=str(prefs))
    assert hb2.is_favorite("Тема") is True
    assert hb2.toggle_favorite("Тема") is False
    hb3 = QAHandbook(prefs_path=str(prefs))
    assert hb3.is_favorite("Тема") is False


def test_studied_progress_and_coexist(tmp_path):
    prefs = str(tmp_path / "p.json")
    hb = QAHandbook(prefs_path=prefs)
    done, total = hb.progress()
    assert done == 0 and total > 0
    q = next(it["question"] for items in hb.get_all_sections().values() for it in items)
    assert hb.toggle_studied(q) is True
    assert hb.progress()[0] == 1
    # избранное и «изучено» живут в одном файле и не затирают друг друга
    hb.toggle_favorite(q)
    hb2 = QAHandbook(prefs_path=prefs)
    assert hb2.is_studied(q) and hb2.is_favorite(q)


def test_handbook_answers_nonempty():
    sections = QAHandbook(track="qa").get_all_sections()
    for items in sections.values():
        for it in items:
            assert it.get("question"), "пустой вопрос"
            assert it.get("answer", "").strip(), f"пустой ответ у {it.get('question')}"
