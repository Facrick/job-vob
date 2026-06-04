"""Тесты банка упражнений: хранение, прогресс и валидатор задания (Role A)."""
from core.ai_engine import LetterAnalyzer
from core.exercises import ExerciseBank


def _bank(tmp_path, seed=None):
    seed_path = None
    if seed is not None:
        import json
        seed_path = tmp_path / "seed.json"
        seed_path.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    return ExerciseBank(
        seed_path=seed_path,
        custom_path=tmp_path / "custom.json",
        progress_path=tmp_path / "progress.json",
    )


def test_add_and_get_for_topic_persist(tmp_path):
    bank = _bank(tmp_path)
    assert bank.get_for_topic("Тема") == []
    bank.add("Тема", {"task": "T", "reference": "R", "rubric": "K"})
    got = bank.get_for_topic("Тема")
    assert len(got) == 1 and got[0]["task"] == "T"
    # перечитываем с диска
    bank2 = _bank(tmp_path)
    assert bank2.get_for_topic("Тема")[0]["reference"] == "R"


def test_add_ignores_empty(tmp_path):
    bank = _bank(tmp_path)
    bank.add("Тема", {})
    bank.add("Тема", {"reference": "только эталон"})
    assert bank.get_for_topic("Тема") == []


def test_seed_then_custom_order(tmp_path):
    bank = _bank(tmp_path, seed={"Тема": [{"task": "seed"}]})
    bank.add("Тема", {"task": "custom"})
    tasks = [e["task"] for e in bank.get_for_topic("Тема")]
    assert tasks == ["seed", "custom"]  # seed первым


def test_progress_best_attempts_passed(tmp_path):
    bank = _bank(tmp_path)
    assert bank.get_progress("Тема") is None
    bank.record_result("Тема", 50, "Частично")
    p = bank.get_progress("Тема")
    assert p["best_score"] == 50 and p["attempts"] == 1 and p["passed"] is False
    bank.record_result("Тема", 80, "Зачтено")
    p = bank.get_progress("Тема")
    assert p["best_score"] == 80 and p["attempts"] == 2 and p["passed"] is True
    # балл ниже лучшего не понижает best, но passed остаётся
    bank.record_result("Тема", 30, "Не зачтено")
    p = bank.get_progress("Тема")
    assert p["best_score"] == 80 and p["passed"] is True and p["last_score"] == 30


def test_progress_persist_and_stats(tmp_path):
    bank = _bank(tmp_path)
    bank.record_result("A", 90, "Зачтено")
    bank.record_result("B", 40, "Частично")
    assert bank.stats() == (1, 2)  # зачтено 1, опробовано 2
    bank2 = _bank(tmp_path)
    assert bank2.stats() == (1, 2)
    assert bank2.get_progress("A")["passed"] is True


def test_record_result_clamps_score(tmp_path):
    bank = _bank(tmp_path)
    bank.record_result("X", 250)
    bank.record_result("Y", -10)
    assert bank.get_progress("X")["best_score"] == 100
    assert bank.get_progress("Y")["best_score"] == 0


# ── Валидатор задания (Role A) ────────────────────────────────────────
class _FakeAnalyzer:
    """Подменяет генерацию/валидацию, чтобы проверить логику ретраев без сети."""

    def __init__(self, gens, vals):
        self._gens = list(gens)
        self._vals = list(vals)

    def generate_exercise(self, *_a, **_k):
        return self._gens.pop(0)

    def validate_exercise(self, *_a, **_k):
        return self._vals.pop(0)

    # переиспользуем реальную логику-обёртку как метод
    generate_validated_exercise = LetterAnalyzer.generate_validated_exercise


def test_validated_accepts_first_valid():
    fa = _FakeAnalyzer(
        gens=[{"task": "ok", "reference": "r", "rubric": "k"}],
        vals=[{"valid": True, "reason": "", "fixed_task": ""}],
    )
    ex = fa.generate_validated_exercise("Тема", "контент")
    assert ex["task"] == "ok"


def test_validated_retries_until_valid():
    fa = _FakeAnalyzer(
        gens=[{"task": "плохое"}, {"task": "хорошее"}],
        vals=[
            {"valid": False, "reason": "не по теме", "fixed_task": ""},
            {"valid": True, "reason": "", "fixed_task": ""},
        ],
    )
    ex = fa.generate_validated_exercise("Тема", "контент", max_attempts=2)
    assert ex["task"] == "хорошее"


def test_validated_applies_fixed_task():
    fa = _FakeAnalyzer(
        gens=[{"task": "сырое", "reference": "r", "rubric": "k"}],
        vals=[{"valid": False, "reason": "уточнить", "fixed_task": "починенное"}],
    )
    ex = fa.generate_validated_exercise("Тема", "контент")
    assert ex["task"] == "починенное" and ex["reference"] == "r"


def test_validated_falls_back_to_last_when_all_invalid():
    fa = _FakeAnalyzer(
        gens=[{"task": "a"}, {"task": "b"}],
        vals=[
            {"valid": False, "reason": "x", "fixed_task": ""},
            {"valid": False, "reason": "y", "fixed_task": ""},
        ],
    )
    ex = fa.generate_validated_exercise("Тема", "контент", max_attempts=2)
    assert ex["task"] == "b"  # последнее сгенерированное, чтобы юзер не остался без задачи
