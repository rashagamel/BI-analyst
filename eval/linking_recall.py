"""Free diagnostic (no LLM, no key): does schema linking pick every table the reference SQL needs?
   python -m eval.linking_recall --questions eval/questions_v2.jsonl --db-url sqlite:///data/saas.db
A question counts as a hit only if ALL tables used by its reference SQL are in the linked set."""
from __future__ import annotations

import argparse

import sqlglot
from sqlglot import exp

from bi_analyst.agents.schema_agent import link_schema
from bi_analyst.config import Settings
from bi_analyst.db import Database

from .run import DEFAULT_QUESTIONS, load_questions


def needed_tables(sql: str, known: set[str]) -> set[str]:
    tree = sqlglot.parse_one(sql, read="sqlite")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    return {t.name for t in tree.find_all(exp.Table) if t.name.lower() in {k.lower() for k in known} and t.name.lower() not in ctes}


def compute(questions: list[dict], db: Database, top_k: int = 6) -> dict:
    schema = db.schema()
    known = set(schema.tables)
    rows, hits = [], 0
    answerable = [q for q in questions if q.get("kind", "answerable") == "answerable" and q.get("gold_sql")]
    for q in answerable:
        need = needed_tables(q["gold_sql"], known)
        got = set(link_schema(q["question"], schema, top_k))
        missing = sorted(need - got)
        hits += not missing
        rows.append({"id": q["id"], "needed": sorted(need), "linked": len(got), "missing": missing})
    return {"n": len(answerable), "hits": hits, "recall": round(hits / len(answerable), 4) if answerable else None,
            "avg_tables_linked": round(sum(r["linked"] for r in rows) / len(rows), 2) if rows else None,
            "n_tables": len(known), "misses": [r for r in rows if r["missing"]]}


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(prog="python -m eval.linking_recall")
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    ap.add_argument("--db-url")
    ap.add_argument("--top-k", type=int, default=Settings().schema_top_k)
    a = ap.parse_args(argv)
    db = Database(a.db_url or Settings().db_url)
    res = compute(load_questions(a.questions), db, a.top_k)
    print(f"Schema linking (top_k={a.top_k}, {res['n_tables']} tables): all needed tables found for "
          f"{res['hits']}/{res['n']} questions ({res['recall']:.0%}); avg tables sent to the model: {res['avg_tables_linked']}")
    for m in res["misses"]:
        print(f"  MISS {m['id']}: needs {m['needed']}, missing {m['missing']}")
    return res


if __name__ == "__main__":
    main()
