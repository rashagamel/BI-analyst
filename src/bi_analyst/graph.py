from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from .agents import data_validator, planner, schema_agent, sql_writer, validator
from .agents.corrector import classify
from .config import Settings
from .db import Database, SchemaInfo
from .llm import LLM
from .state import AnalystState
from .tracing import Tracer


@dataclass
class Deps:
    """Everything the nodes need, injected once. No module-level globals."""
    llm: LLM
    db: Database
    schema: SchemaInfo
    settings: Settings
    tracer: Tracer


def build_graph(d: Deps):
    # ---------------- nodes ----------------
    def plan_node(s: AnalystState) -> dict:
        return {"plan": planner.plan(d.llm, s["question"]), "attempts": 0, "history": [], "error": None}

    def schema_node(s: AnalystState) -> dict:
        tables = schema_agent.link_schema(s["question"], d.schema, d.settings.schema_top_k)
        return {"linked_tables": tables, "schema_context": d.schema.render(tables)}

    def write_node(s: AnalystState) -> dict:
        sql = sql_writer.write_sql(
            d.llm, dialect=d.db.dialect, question=s["question"], plan=s["plan"],
            schema_context=s["schema_context"], history=s.get("history", []),
        )
        return {"sql": sql, "attempts": s.get("attempts", 0) + 1}

    def _fail(s: AnalystState, error: str) -> dict:
        hist = list(s.get("history", []))
        hist.append({"sql": s["sql"], "error": error, "error_type": classify(error)})
        return {"error": error, "history": hist}

    def validate_node(s: AnalystState) -> dict:
        err = validator.validate_sql(s["sql"], d.schema, d.db)
        return _fail(s, err) if err else {"error": None}

    def execute_node(s: AnalystState) -> dict:
        try:
            res = d.db.run(s["sql"])
        except Exception as e:  # noqa: BLE001
            return _fail(s, f"{e.__class__.__name__}: {getattr(e, 'orig', e)}")
        return {"error": None, "columns": res.columns, "rows": res.rows, "truncated": res.truncated}

    def check_node(s: AnalystState) -> dict:
        return {"warnings": data_validator.check_results(s["columns"], s["rows"], s["truncated"]),
                "status": "success"}

    def fail_node(s: AnalystState) -> dict:
        return {"status": "failed"}

    # ---------------- routing ----------------
    def after_validate(s: AnalystState) -> str:
        if not s.get("error"):
            return "execute"
        return "write_sql" if s["attempts"] < d.settings.max_attempts else "fail"

    def after_execute(s: AnalystState) -> str:
        if not s.get("error"):
            return "check_results"
        return "write_sql" if s["attempts"] < d.settings.max_attempts else "fail"

    # ---------------- graph ----------------
    t = d.tracer.wrap
    g = StateGraph(AnalystState)
    for name, fn in [("plan", plan_node), ("schema_link", schema_node), ("write_sql", write_node),
                     ("validate", validate_node), ("execute", execute_node),
                     ("check_results", check_node), ("fail", fail_node)]:
        g.add_node(name, t(name, fn))
    g.add_edge(START, "plan")
    g.add_edge("plan", "schema_link")
    g.add_edge("schema_link", "write_sql")
    g.add_edge("write_sql", "validate")
    g.add_conditional_edges("validate", after_validate,
                            {"execute": "execute", "write_sql": "write_sql", "fail": "fail"})
    g.add_conditional_edges("execute", after_execute,
                            {"check_results": "check_results", "write_sql": "write_sql", "fail": "fail"})
    g.add_edge("check_results", END)
    g.add_edge("fail", END)
    return g.compile()
