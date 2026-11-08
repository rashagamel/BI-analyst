from bi_analyst import BIAnalyst
from bi_analyst.agents.data_validator import check_results
from bi_analyst.agents.schema_agent import link_schema
from bi_analyst.llm import FakeLLM

GOOD_SQL = """```sql
SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
FROM order_items oi
JOIN products p ON p.product_id = oi.product_id
JOIN orders o ON o.order_id = oi.order_id
WHERE o.status = 'completed'
GROUP BY p.category
ORDER BY revenue DESC
```"""
BAD_COLUMN_SQL = "```sql\nSELECT category, SUM(revenue) AS revenue FROM products GROUP BY category\n```"


def test_happy_path(settings):
    llm = FakeLLM({"planner": ["Measure: revenue by category."], "sql_writer": [GOOD_SQL]})
    r = BIAnalyst(settings, llm=llm).ask("What is revenue by product category?")
    assert r["status"] == "success" and r["attempts"] == 1
    assert r["columns"] == ["category", "revenue"] and len(r["rows"]) == 4
    assert r["rows"][0][1] >= r["rows"][-1][1]


def test_self_correction_recovers(settings):
    llm = FakeLLM({"planner": ["plan"], "sql_writer": [BAD_COLUMN_SQL, GOOD_SQL]})
    r = BIAnalyst(settings, llm=llm).ask("What is revenue by product category?")
    assert r["status"] == "success" and r["attempts"] == 2
    assert r["history"][0]["error_type"] == "unknown_column"
    # the corrector must have shown the model its previous error
    second_prompt = [u for a, u in llm.calls if a == "sql_writer"][1]
    assert "PREVIOUS FAILED ATTEMPTS" in second_prompt and "unknown_column" in second_prompt


def test_gives_up_after_max_attempts(settings):
    llm = FakeLLM({"planner": ["plan"], "sql_writer": [BAD_COLUMN_SQL]})
    r = BIAnalyst(settings, llm=llm).ask("revenue by category")
    assert r["status"] == "failed" and r["attempts"] == settings.max_attempts


def test_destructive_sql_never_executes(settings):
    llm = FakeLLM({"planner": ["plan"], "sql_writer": ["DROP TABLE customers"]})
    a = BIAnalyst(settings, llm=llm)
    r = a.ask("delete everything")
    assert r["status"] == "failed"
    assert "customers" in a.db.schema().tables  # still there


def test_trace_written(settings):
    import pathlib
    llm = FakeLLM({"planner": ["plan"], "sql_writer": [GOOD_SQL]})
    r = BIAnalyst(settings, llm=llm).ask("revenue by category")
    trace = pathlib.Path(settings.trace_dir) / f"{r['trace_id']}.jsonl"
    assert trace.exists() and len(trace.read_text().splitlines()) >= 5


def test_schema_linking_picks_relevant_tables(db):
    tables = link_schema("revenue by product category", db.schema(), top_k=3)
    assert "products" in tables and "order_items" in tables


def test_data_validator_flags_issues():
    w = check_results(["region", "revenue"], [["EU", -5.0], ["US", None]], False)
    assert any("negative" in x for x in w)
    assert check_results(["a"], [], False)[0].startswith("Query returned no rows")
