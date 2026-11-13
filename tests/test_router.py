import dataclasses
import json
import pathlib

from bi_analyst import BIAnalyst
from bi_analyst.agents.context import format_prior_results
from bi_analyst.agents.router import parse_route
from bi_analyst.db import _jsonable
from bi_analyst.llm import FakeLLM

Q = "revenue by category and customers by region"
CAT_SQL = """```sql
SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
FROM order_items oi JOIN products p ON p.product_id = oi.product_id
GROUP BY p.category
```"""
REGION_SQL = "```sql\nSELECT region, COUNT(*) AS customers FROM customers GROUP BY region\n```"
BAD_SQL = "```sql\nSELECT nonexistent_col FROM customers\n```"
MULTI = json.dumps({"route": "multi_step", "sub_questions": ["Revenue by product category?", "Customers per region?"]})
SIMPLE = json.dumps({"route": "simple", "sub_questions": []})


def router_settings(settings):
    return dataclasses.replace(settings, enable_router=True)


# ---- parsing: every bad input must fall back to the simple path ----
def test_parse_valid_multi():
    assert parse_route(MULTI, Q) == ("multi_step", ["Revenue by product category?", "Customers per region?"])


def test_parse_fenced_json():
    assert parse_route(f"```json\n{MULTI}\n```", Q)[0] == "multi_step"


def test_parse_garbage_falls_back():
    assert parse_route("I think this is simple!", Q) == ("simple", [Q])
    assert parse_route("{not json}", Q) == ("simple", [Q])


def test_parse_single_sub_question_is_simple():
    one = json.dumps({"route": "multi_step", "sub_questions": ["only one"]})
    assert parse_route(one, Q) == ("simple", [Q])


def test_parse_caps_sub_questions():
    many = json.dumps({"route": "multi_step", "sub_questions": [f"q{i}" for i in range(9)]})
    assert len(parse_route(many, Q, max_sub=4)[1]) == 4


# ---- end to end ----
def test_simple_route_behaves_like_before(settings):
    llm = FakeLLM({"router": [SIMPLE], "planner": ["plan"], "sql_writer": [REGION_SQL]})
    r = BIAnalyst(router_settings(settings), llm=llm).ask("customers per region")
    assert r["route"] == "simple" and r["status"] == "success"
    assert r["columns"] == ["region", "customers"] and r["sub_results"] == []


def test_multi_step_runs_each_sub_question(settings):
    llm = FakeLLM({"router": [MULTI], "planner": ["plan"], "sql_writer": [CAT_SQL, REGION_SQL]})
    r = BIAnalyst(router_settings(settings), llm=llm).ask(Q)
    assert r["route"] == "multi_step" and r["status"] == "success"
    assert [s["status"] for s in r["sub_results"]] == ["success", "success"]
    assert r["sub_results"][0]["columns"] == ["category", "revenue"]
    assert r["sub_results"][1]["columns"] == ["region", "customers"]
    # top level mirrors the primary result = last sub-question that succeeded
    assert r["primary_index"] == 2
    assert r["sql"] == r["sub_results"][1]["sql"]
    assert r["columns"] == ["region", "customers"] and r["rows"] == r["sub_results"][1]["rows"]


def test_multi_step_partial_failure(settings):
    llm = FakeLLM({"router": [MULTI], "planner": ["plan"], "sql_writer": [CAT_SQL, BAD_SQL]})
    r = BIAnalyst(router_settings(settings), llm=llm).ask(Q)
    assert r["status"] == "partial"
    assert [s["status"] for s in r["sub_results"]] == ["success", "failed"]
    assert r["sub_results"][1]["attempts"] == settings.max_attempts
    assert r["error"]
    assert r["primary_index"] == 1 and r["columns"] == ["category", "revenue"]


def test_multi_step_all_fail(settings):
    llm = FakeLLM({"router": [MULTI], "planner": ["plan"], "sql_writer": [BAD_SQL]})
    r = BIAnalyst(router_settings(settings), llm=llm).ask(Q)
    assert r["status"] == "failed" and r["primary_index"] == 0 and r["rows"] == []


def test_trace_marks_each_sub_question(settings):
    llm = FakeLLM({"router": [MULTI], "planner": ["plan"], "sql_writer": [CAT_SQL, REGION_SQL]})
    cfg = router_settings(settings)
    r = BIAnalyst(cfg, llm=llm).ask(Q)
    lines = pathlib.Path(cfg.trace_dir, f"{r['trace_id']}.jsonl").read_text().splitlines()
    events = [json.loads(x) for x in lines]
    markers = [e for e in events if e["node"] == "sub_question"]
    assert [m["index"] for m in markers] == [1, 2]
    assert sum(1 for e in events if e["node"] == "write_sql") == 2


def test_router_disabled_makes_no_router_call(settings):
    llm = FakeLLM({"planner": ["plan"], "sql_writer": [REGION_SQL]})
    BIAnalyst(settings, llm=llm).ask("customers per region")
    assert all(agent != "router" for agent, _ in llm.calls)


# ---- float noise fix ----
def test_float_noise_removed():
    assert _jsonable(57297.200000000004) == 57297.2


# ---- dependent sub-questions: later steps see earlier results ----
def test_later_sub_question_receives_earlier_results(settings):
    llm = FakeLLM({"router": [MULTI], "planner": ["plan"], "sql_writer": [CAT_SQL, REGION_SQL]})
    BIAnalyst(router_settings(settings), llm=llm).ask(Q)
    writer = [u for a, u in llm.calls if a == "sql_writer"]
    planner = [u for a, u in llm.calls if a == "planner"]
    assert "EARLIER RESULTS" not in writer[0] and "EARLIER RESULTS" not in planner[0]
    assert "EARLIER RESULTS" in writer[1] and "EARLIER RESULTS" in planner[1]
    assert "Electronics" in writer[1]            # a value from sub-question 1's result
    assert "Revenue by product category?" in writer[1]


def test_trace_records_whether_context_was_passed(settings):
    llm = FakeLLM({"router": [MULTI], "planner": ["plan"], "sql_writer": [CAT_SQL, REGION_SQL]})
    cfg = router_settings(settings)
    r = BIAnalyst(cfg, llm=llm).ask(Q)
    events = [json.loads(x) for x in pathlib.Path(cfg.trace_dir, f"{r['trace_id']}.jsonl").read_text().splitlines()]
    markers = [e for e in events if e["node"] == "sub_question"]
    assert [m["has_prior_context"] for m in markers] == [False, True]


def test_failed_earlier_step_does_not_block_later_ones(settings):
    llm = FakeLLM({"router": [MULTI], "planner": ["plan"], "sql_writer": [BAD_SQL, BAD_SQL, BAD_SQL, REGION_SQL]})
    r = BIAnalyst(router_settings(settings), llm=llm).ask(Q)
    assert [x["status"] for x in r["sub_results"]] == ["failed", "success"]
    assert r["status"] == "partial" and r["primary_index"] == 2
    writer = [u for a, u in llm.calls if a == "sql_writer"]
    assert "STATUS: failed" in writer[-1]        # later step is told the earlier one failed


def test_format_prior_results_limits_size():
    big = {"question": "q", "status": "success", "sql": "SELECT 1", "columns": ["a"],
           "rows": [[i] for i in range(500)]}
    text = format_prior_results([big], max_rows=10, max_chars=400)
    assert "first 10 of 500" in text and len(text) <= 400 + len("\n...(truncated)")
    assert format_prior_results([]) == ""
