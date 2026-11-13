import json
from pathlib import Path

import pytest

from bi_analyst import BIAnalyst
from bi_analyst.db import Database
from oracle import OracleLLM, check_question_set
from eval.compare import mismatch_reason, results_match
from eval.report import aggregate_runs, summarize
from eval.run import evaluate_question, load_questions, main, run_once

QUESTIONS = load_questions(Path(__file__).resolve().parents[1] / "eval" / "questions.jsonl")


@pytest.fixture()
def analyst(settings):
    return BIAnalyst(settings, llm=OracleLLM(QUESTIONS))


@pytest.fixture()
def gold_db(settings):
    return Database(settings.db_url, max_rows=100_000)


# ---------------- comparison rules ----------------
def test_numbers_compare_loosely_text_strictly():
    assert results_match([[5, "a"]], [[5.0, " a "]])
    assert results_match([[1.004]], [[1.0]])
    assert not results_match([["x"]], [["y"]])
    assert not results_match([[5]], [["5"]])


def test_row_order_only_matters_when_ordered():
    a, b = [[1], [2]], [[2], [1]]
    assert results_match(a, b) and not results_match(a, b, ordered=True)
    assert mismatch_reason(a, b, ordered=True) == "order"


def test_duplicates_matter_and_none_is_equal_to_none():
    assert not results_match([[1], [1]], [[1]])
    assert results_match([[None]], [[None]])


@pytest.mark.parametrize("gold,got,reason", [
    ([[1, 2]], [[1]], "column_count"),
    ([[1], [2]], [[1]], "row_count"),
    ([[1]], [], "empty_result"),
    ([[1]], [[2]], "values"),
])
def test_mismatch_reasons(gold, got, reason):
    assert mismatch_reason(gold, got) == reason


# ---------------- the question file itself ----------------
def test_question_set_is_sound(gold_db):
    check_question_set(QUESTIONS, gold_db, min_total=60, min_tricks=10)


# ---------------- end to end ----------------
def test_perfect_model_scores_100_percent(analyst, gold_db, tmp_path):
    recs = run_once(analyst, gold_db, QUESTIONS, 0, tmp_path / "p.jsonl", "t")
    s = summarize(recs)
    assert s["exec_accuracy"] == 1.0 and s["refusal_accuracy"] == 1.0
    assert s["correction_lift"] == 0.0 and s["errors"] == 0
    assert s["n_questions"] == len(QUESTIONS)
    assert s["input_tokens"] > 0                      # usage accounting reached the records


def test_wrong_answers_are_detected_and_classified(settings, gold_db):
    llm = OracleLLM(QUESTIONS, {
        "M15": ["SELECT COUNT(*) FROM order_items"],                       # wrong value
        "E02": ["SELECT region FROM customers GROUP BY region"],           # wrong column count
        "E13": ["SELECT DISTINCT category FROM products WHERE 1 = 0"],     # empty result
    })
    a = BIAnalyst(settings, llm=llm)
    by_id = {q["id"]: q for q in QUESTIONS}
    got = {i: evaluate_question(a, gold_db, by_id[i]) for i in ("M15", "E02", "E13", "E01")}
    assert [got[i]["correct"] for i in ("M15", "E02", "E13", "E01")] == [False, False, False, True]
    assert (got["M15"]["failure_type"], got["E02"]["failure_type"], got["E13"]["failure_type"]) == \
        ("values", "column_count", "empty_result")


def test_correction_lift_is_measured(settings, gold_db):
    gold = next(q for q in QUESTIONS if q["id"] == "E01")["gold_sql"]
    llm = OracleLLM(QUESTIONS, {"E01": ["SELECT nope FROM customers", gold]})  # first attempt fails validation
    a = BIAnalyst(settings, llm=llm)
    recs = [evaluate_question(a, gold_db, next(q for q in QUESTIONS if q["id"] == i)) for i in ("E01", "E03")]
    assert recs[0]["correct"] and recs[0]["attempts"] == 2 and not recs[0]["first_attempt_correct"]
    assert recs[1]["first_attempt_correct"]
    s = summarize(recs)
    assert s["exec_accuracy"] == 1.0 and s["first_attempt_accuracy"] == 0.5 and s["correction_lift"] == 0.5
    assert recs[0]["error_types"] == ["unknown_column"]


def test_answering_an_unanswerable_question_counts_as_failure(settings, gold_db):
    llm = OracleLLM(QUESTIONS, {"T01": ["SELECT COUNT(*) FROM customers"]})  # makes up an answer
    rec = evaluate_question(BIAnalyst(settings, llm=llm), gold_db, next(q for q in QUESTIONS if q["id"] == "T01"))
    assert not rec["correct"] and rec["failure_type"] == "answered_instead_of_refusing"


def test_api_errors_are_recorded_not_raised(settings, gold_db):
    class Boom:
        def complete(self, *a, **k):
            raise RuntimeError("429 rate limit")
    rec = evaluate_question(BIAnalyst(settings, llm=Boom()), gold_db, QUESTIONS[0])
    assert rec["status"] == "error" and rec["failure_type"] == "api_error" and "429" in rec["error"]


def test_aggregate_runs():
    agg = aggregate_runs([{"exec_accuracy": 0.8, "first_attempt_accuracy": 0.7, "correction_lift": 0.1, "refusal_accuracy": 1.0},
                          {"exec_accuracy": 0.6, "first_attempt_accuracy": 0.6, "correction_lift": 0.0, "refusal_accuracy": 1.0}])
    assert agg["exec_accuracy"] == {"mean": 0.7, "min": 0.6, "max": 0.8}


def test_cli_writes_reports_without_secrets(demo_db, tmp_path, monkeypatch):
    monkeypatch.setenv("BI_DB_URL", demo_db)
    monkeypatch.setenv("BI_API_KEY", "SECRET-KEY-123")
    monkeypatch.setenv("BI_TRACE_DIR", str(tmp_path / "traces"))
    out = main(["--name", "t", "--out-dir", str(tmp_path), "--smoke", "--repeat", "2"], llm=OracleLLM(QUESTIONS))
    md, js = (tmp_path / "t.md").read_text(), (tmp_path / "t.json").read_text()
    assert out["aggregate"]["exec_accuracy"]["mean"] == 1.0 and out["aggregate"]["n_runs"] == 2
    assert "Execution accuracy" in md and "SECRET-KEY-123" not in md + js and demo_db not in md + js
    assert not (tmp_path / "t.partial.jsonl").exists()
    assert len(json.loads(js)["runs"]) == 2
