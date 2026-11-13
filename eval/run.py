"""Run the evaluation:  python -m eval.run --name baseline   (see eval/README.md)"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

from bi_analyst import BIAnalyst
from bi_analyst.config import Settings
from bi_analyst.db import Database
from bi_analyst.llm import LLM

from .compare import mismatch_reason, results_match
from .report import aggregate_runs, summarize, to_markdown

DEFAULT_QUESTIONS = Path(__file__).parent / "questions.jsonl"
SMOKE_IDS = ["E01", "E02", "M01", "M03", "H01", "T01"]  # cheap first run: 6 questions


def load_questions(path: str | Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_question(analyst: BIAnalyst, gold_db: Database, q: dict) -> dict:
    kind = q.get("kind", "answerable")
    rec: dict[str, Any] = {
        "id": q["id"], "kind": kind, "difficulty": q.get("difficulty", "medium"), "tags": q.get("tags", []),
        "question": q["question"], "gold_sql": q.get("gold_sql"), "status": "error", "correct": False,
        "first_attempt_correct": False, "attempts": 0, "route": None, "sql": None, "error": None,
        "failure_type": None, "rows_got": None, "rows_expected": None, "error_types": [],
        "seconds": 0.0, "llm_calls": 0, "input_tokens": 0, "output_tokens": 0,
    }
    t0 = time.perf_counter()
    try:
        res = analyst.ask(q["question"])
    except Exception as e:  # noqa: BLE001  (API errors, rate limits, ...)
        rec["seconds"] = round(time.perf_counter() - t0, 2)
        rec["error"] = f"{e.__class__.__name__}: {e}"
        rec["failure_type"] = "api_error"
        return rec
    rec["seconds"] = round(time.perf_counter() - t0, 2)

    u = res["usage"]["total"]
    rec.update({
        "status": res["status"], "attempts": res["attempts"], "route": res["route"], "sql": res["sql"],
        "error": res["error"], "rows_got": len(res["rows"]), "llm_calls": u["calls"],
        "input_tokens": u["input_tokens"], "output_tokens": u["output_tokens"],
        "error_types": [h["error_type"] for h in res.get("history", [])],
    })

    if kind != "answerable":  # unanswerable / unsafe: the right behaviour is to NOT produce a result
        rec["correct"] = res["status"] in ("failed", "unanswerable")
        rec["first_attempt_correct"] = rec["correct"]
        rec["failure_type"] = None if rec["correct"] else "answered_instead_of_refusing"
        return rec

    golds = [gold_db.run(g) for g in [q["gold_sql"], *q.get("alt_gold_sql", [])]]
    ordered = bool(q.get("ordered", False))
    rec["rows_expected"] = len(golds[0].rows)
    if res["status"] == "success":
        rec["correct"] = any(results_match(g.rows, res["rows"], ordered) for g in golds)
        if not rec["correct"]:
            rec["failure_type"] = mismatch_reason(golds[0].rows, res["rows"], ordered)
    else:
        rec["failure_type"] = "refused_answerable" if res["status"] == "unanswerable" else "pipeline_failed"
    rec["first_attempt_correct"] = rec["correct"] and res["attempts"] == 1
    return rec


def run_once(analyst: BIAnalyst, gold_db: Database, questions: list[dict], sleep: float,
             partial_path: Path, label: str) -> list[dict]:
    records, consecutive_errors = [], 0
    for i, q in enumerate(questions, 1):
        rec = evaluate_question(analyst, gold_db, q)
        records.append(rec)
        with open(partial_path, "a", encoding="utf-8") as f:   # results survive a crash or rate limit
            f.write(json.dumps(rec, default=str) + "\n")
        print(f"[{label} {i}/{len(questions)}] {q['id']:<4} {'OK  ' if rec['correct'] else 'FAIL'} "
              f"status={rec['status']} attempts={rec['attempts']} {rec['seconds']}s"
              + (f"  ({rec['failure_type']})" if rec["failure_type"] else ""), flush=True)
        consecutive_errors = consecutive_errors + 1 if rec["status"] == "error" else 0
        if consecutive_errors >= 3:
            raise SystemExit(f"Stopping: 3 errors in a row (partial results in {partial_path}). "
                             f"Last error: {rec['error']}\nCheck your key, model name (BI_MODEL) and rate limits.")
        if sleep:
            time.sleep(sleep)
    return records


def main(argv: list[str] | None = None, llm: LLM | None = None) -> dict:
    ap = argparse.ArgumentParser(prog="python -m eval.run")
    ap.add_argument("--name", default=dt.datetime.now().strftime("run-%Y%m%d-%H%M%S"))
    ap.add_argument("--questions", default=str(DEFAULT_QUESTIONS))
    ap.add_argument("--out-dir", default="eval/results")
    ap.add_argument("--ids", help="comma-separated question ids to run, e.g. E01,M03")
    ap.add_argument("--smoke", action="store_true", help=f"run only {', '.join(SMOKE_IDS)} (cheap first test)")
    ap.add_argument("--limit", type=int, help="run only the first N selected questions")
    ap.add_argument("--repeat", type=int, default=1, help="repeat the whole run N times and average")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds to wait between questions (free-tier limits)")
    ap.add_argument("--router", action="store_true", help="enable the router (default: off, to score single-query SQL)")
    ap.add_argument("--max-attempts", type=int, help="SQL attempts per question (1 = no self-correction)")
    ap.add_argument("--db-url", help="database to test against, e.g. sqlite:///data/saas.db (default: BI_DB_URL)")
    ap.add_argument("--provider")
    ap.add_argument("--model")
    ap.add_argument("--price-in", type=float, help="USD per 1M input tokens (optional, for cost)")
    ap.add_argument("--price-out", type=float, help="USD per 1M output tokens (optional, for cost)")
    args = ap.parse_args(argv)

    settings = dataclasses.replace(Settings(), enable_router=args.router)
    if args.max_attempts:
        settings = dataclasses.replace(settings, max_attempts=args.max_attempts)
    if args.db_url:
        settings = dataclasses.replace(settings, db_url=args.db_url)
    if args.provider:
        settings = dataclasses.replace(settings, provider=args.provider.lower())
    if args.model:
        settings = dataclasses.replace(settings, model=args.model)

    questions = load_questions(args.questions)
    if args.smoke:
        questions = [q for q in questions if q["id"] in SMOKE_IDS]
    if args.ids:
        wanted = {x.strip() for x in args.ids.split(",")}
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        raise SystemExit("No questions selected.")

    analyst = BIAnalyst(settings, llm=llm)
    gold_db = Database(settings.db_url, max_rows=100_000, timeout_s=60)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    partial = out_dir / f"{args.name}.partial.jsonl"
    partial.unlink(missing_ok=True)

    runs = []
    for k in range(1, args.repeat + 1):
        records = run_once(analyst, gold_db, questions, args.sleep, partial, f"run {k}/{args.repeat}")
        runs.append({"summary": summarize(records, args.price_in, args.price_out), "records": records})
    aggregate = aggregate_runs([r["summary"] for r in runs])

    config = {  # never write keys or database URLs (they can contain passwords)
        "date": dt.datetime.now().isoformat(timespec="seconds"),
        "provider": settings.provider, "model": settings.model,
        "router": settings.enable_router, "max_attempts": settings.max_attempts,
        "db_dialect": analyst.db.dialect, "questions_file": Path(args.questions).name,
        "n_questions": len(questions), "repeat": args.repeat,
    }
    (out_dir / f"{args.name}.json").write_text(
        json.dumps({"name": args.name, "config": config, "aggregate": aggregate, "runs": runs}, indent=2, default=str),
        encoding="utf-8")
    (out_dir / f"{args.name}.md").write_text(to_markdown(args.name, config, runs, aggregate), encoding="utf-8")
    partial.unlink(missing_ok=True)

    s = runs[0]["summary"]
    print(f"\nExecution accuracy: {s['exec_accuracy']}  first-attempt: {s['first_attempt_accuracy']}  "
          f"refusal: {s['refusal_accuracy']}  errors: {s['errors']}")
    print(f"Wrote {out_dir / (args.name + '.md')} and {out_dir / (args.name + '.json')}")
    return {"aggregate": aggregate, "runs": runs}


if __name__ == "__main__":
    main()
