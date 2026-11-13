from __future__ import annotations

from dataclasses import dataclass

from langgraph.graph import END, START, StateGraph

from .agents import data_validator, planner, router, schema_agent, sql_writer, validator
from .agents.context import format_prior_results
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


def build_sql_graph(d: Deps):
    """The single-question pipeline: plan -> link -> write -> validate -> execute -> check."""
    # ---------------- nodes ----------------
    def plan_node(s: AnalystState) -> dict:
        return {"plan": planner.plan(d.llm, s["question"], s.get("prior_context", "")),
                "attempts": 0, "history": [], "error": None, "unanswerable": ""}

    def schema_node(s: AnalystState) -> dict:
        tables = schema_agent.link_schema(s["question"] + " " + s.get("prior_context", ""), d.schema, d.settings.schema_top_k)
        return {"linked_tables": tables, "schema_context": d.schema.render(tables)}

    def write_node(s: AnalystState) -> dict:
        sql = sql_writer.write_sql(
            d.llm, dialect=d.db.dialect, question=s["question"], plan=s["plan"],
            schema_context=s["schema_context"], history=s.get("history", []),
            context=s.get("prior_context", ""),
        )
        attempts = s.get("attempts", 0) + 1
        if sql_writer.is_cannot_answer(sql):
            reason = sql_writer.cannot_answer_reason(sql)
            return {"sql": "", "attempts": attempts, "unanswerable": reason, "error": f"CANNOT_ANSWER: {reason}"}
        return {"sql": sql, "attempts": attempts}

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
        return {"status": "unanswerable" if s.get("unanswerable") else "failed"}

    # ---------------- routing ----------------
    def after_write(s: AnalystState) -> str:
        return "fail" if s.get("unanswerable") else "validate"

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
    g.add_conditional_edges("write_sql", after_write, {"validate": "validate", "fail": "fail"})
    g.add_conditional_edges("validate", after_validate,
                            {"execute": "execute", "write_sql": "write_sql", "fail": "fail"})
    g.add_conditional_edges("execute", after_execute,
                            {"check_results": "check_results", "write_sql": "write_sql", "fail": "fail"})
    g.add_edge("check_results", END)
    g.add_edge("fail", END)
    return g.compile()


def build_graph(d: Deps):
    """Top-level graph: router -> (simple: one pipeline run | multi_step: one run per sub-question)."""
    sql_graph = build_sql_graph(d)

    def router_node(s: AnalystState) -> dict:
        if not d.settings.enable_router:
            return {"route": "simple", "sub_questions": [s["question"]]}
        route, subs = router.route_question(
            d.llm, s["question"], list(d.schema.tables), d.settings.max_sub_questions)
        return {"route": route, "sub_questions": subs}

    def single_node(s: AnalystState) -> dict:
        return sql_graph.invoke({"question": s["question"], "trace_id": s["trace_id"]})

    def multi_node(s: AnalystState) -> dict:
        results: list[dict] = []
        context = ""
        for i, q in enumerate(s["sub_questions"], 1):
            d.tracer.emit(s["trace_id"], "sub_question", {"index": i, "question": q,
                                                          "has_prior_context": bool(context)})
            out = sql_graph.invoke({"question": q, "trace_id": s["trace_id"], "prior_context": context})
            results.append({
                "question": q, "status": out.get("status", "failed"), "plan": out.get("plan"),
                "sql": out.get("sql"), "attempts": out.get("attempts", 0),
                "columns": out.get("columns", []), "rows": out.get("rows", []),
                "truncated": out.get("truncated", False),
                "warnings": out.get("warnings", []), "error": out.get("error"),
            })
            context = format_prior_results(results)   # later sub-questions see earlier results
        ok = [r["status"] == "success" for r in results]
        status = "success" if all(ok) else ("partial" if any(ok) else "failed")
        # Top-level fields mirror the PRIMARY result: the last sub-question that succeeded. For a
        # chained question that is the final answer. For independent questions it is just one of
        # several tables, so read `sub_results` for all of them.
        primary_i = max((i for i, r in enumerate(results, 1) if r["status"] == "success"), default=0)
        update = {
            "sub_results": results,
            "status": status,
            "primary_index": primary_i,
            "attempts": sum(r["attempts"] for r in results),
            "warnings": [f"[sub-question {i}] {w}" for i, r in enumerate(results, 1) for w in r["warnings"]],
            "error": next((r["error"] for r in results if r["error"]), None),
        }
        if primary_i:
            p = results[primary_i - 1]
            update.update({"plan": p["plan"], "sql": p["sql"], "columns": p["columns"],
                           "rows": p["rows"], "truncated": p["truncated"]})
        return update

    t = d.tracer.wrap
    g = StateGraph(AnalystState)
    g.add_node("router", t("router", router_node))
    g.add_node("run_single", t("run_single", single_node))
    g.add_node("run_multi", t("run_multi", multi_node))
    g.add_edge(START, "router")
    g.add_conditional_edges("router", lambda s: "run_multi" if s.get("route") == "multi_step" else "run_single",
                            {"run_single": "run_single", "run_multi": "run_multi"})
    g.add_edge("run_single", END)
    g.add_edge("run_multi", END)
    return g.compile()
