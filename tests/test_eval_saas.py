import sqlite3
from pathlib import Path

import pytest

from bi_analyst.db import Database
from bi_analyst.demo_data import create_saas_db
from eval import linking_recall
from eval.run import load_questions, main
from oracle import OracleLLM, check_question_set

ROOT = Path(__file__).resolve().parents[1]
V2_FILE = ROOT / "eval" / "questions_v2.jsonl"
V2 = load_questions(V2_FILE)


@pytest.fixture(scope="session")
def saas_url(tmp_path_factory):
    return f"sqlite:///{create_saas_db(str(tmp_path_factory.mktemp('saas') / 'saas.db'))}"


@pytest.fixture()
def saas_db(saas_url):
    return Database(saas_url, max_rows=100_000)


def _q(con, sql):
    return con.execute(sql).fetchall()


def test_saas_database_shape_and_deliberate_mess(saas_url):
    con = sqlite3.connect(saas_url.removeprefix("sqlite:///"))
    tables = {r[0] for r in _q(con, "SELECT name FROM sqlite_master WHERE type='table'")}
    assert len(tables) == 13 and {"fx_rates", "refunds", "invoice_items", "usage_events"} <= tables
    cats = {r[0] for r in _q(con, "SELECT DISTINCT category FROM tickets")}
    assert {"billing", "Billing", "BILLING"} <= cats                      # mixed-case categories
    assert _q(con, "SELECT COUNT(*) FROM tickets WHERE csat_score IS NULL")[0][0] > 0
    assert _q(con, "SELECT COUNT(*) FROM accounts WHERE deleted_at IS NOT NULL")[0][0] > 0
    assert _q(con, "SELECT COUNT(DISTINCT currency) FROM invoices")[0][0] == 3
    assert _q(con, "SELECT COUNT(*) FROM (SELECT email FROM contacts GROUP BY email HAVING COUNT(DISTINCT account_id) > 1)")[0][0] > 0
    assert _q(con, "SELECT COUNT(*) FROM invoices WHERE subscription_id NOT IN (SELECT subscription_id FROM subscriptions)")[0][0] == 0
    assert _q(con, "SELECT COUNT(*) FROM accounts WHERE status='churned' AND churned_at IS NULL")[0][0] == 0


def test_saas_database_is_deterministic(tmp_path):
    def fingerprint(name):
        con = sqlite3.connect(create_saas_db(str(tmp_path / name)))
        return [_q(con, f"SELECT COUNT(*), ROUND(SUM(total), 2) FROM invoices"), _q(con, "SELECT COUNT(*) FROM tickets"),
                _q(con, "SELECT group_concat(company_name) FROM (SELECT company_name FROM accounts ORDER BY account_id LIMIT 20)")]
    assert fingerprint("a.db") == fingerprint("b.db")


def test_v2_question_set_is_sound(saas_db):
    check_question_set(V2, saas_db, min_total=50, min_tricks=9)


def test_perfect_model_scores_100_percent_on_v2(saas_url, tmp_path, monkeypatch):
    monkeypatch.setenv("BI_TRACE_DIR", str(tmp_path / "traces"))
    out = main(["--name", "v2", "--out-dir", str(tmp_path), "--questions", str(V2_FILE), "--db-url", saas_url],
               llm=OracleLLM(V2))
    s = out["runs"][0]["summary"]
    assert s["exec_accuracy"] == 1.0 and s["refusal_accuracy"] == 1.0 and s["n_questions"] == len(V2)


def test_linking_recall_is_complete_on_the_small_demo(demo_db):
    res = linking_recall.compute(load_questions(ROOT / "eval" / "questions.jsonl"), Database(demo_db))
    assert res["recall"] == 1.0


def test_linking_recall_on_v2_runs_and_documents_the_known_gap(saas_db):
    res = linking_recall.compute(V2, saas_db)
    assert res["n_tables"] == 13 and res["recall"] >= 0.8
    # known weakness: "in USD" does not mention exchange rates, so fx_rates is not linked
    assert all(set(m["missing"]) <= {"fx_rates"} for m in res["misses"])
