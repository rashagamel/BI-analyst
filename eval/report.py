"""Aggregation and Markdown reporting for evaluation runs."""
from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
from typing import Any

DIFFICULTIES = ["easy", "medium", "hard"]


def _rate(xs: list[bool]) -> float | None:
    return round(sum(1 for x in xs if x) / len(xs), 4) if xs else None


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def summarize(records: list[dict], price_in: float | None = None, price_out: float | None = None) -> dict:
    """Headline numbers. Execution accuracy and correction lift are computed on ANSWERABLE
    questions only; unanswerable/unsafe questions are scored separately as refusal accuracy."""
    answerable = [r for r in records if r["kind"] == "answerable"]
    refusal = [r for r in records if r["kind"] != "answerable"]
    exec_acc = _rate([r["correct"] for r in answerable])
    first_acc = _rate([r["first_attempt_correct"] for r in answerable])

    by_diff = {}
    for d in DIFFICULTIES:
        sub = [r for r in answerable if r["difficulty"] == d]
        if sub:
            by_diff[d] = {"n": len(sub), "accuracy": _rate([r["correct"] for r in sub])}
    tag_buckets: dict[str, list[bool]] = defaultdict(list)
    for r in answerable:
        for t in r["tags"]:
            tag_buckets[t].append(r["correct"])
    by_tag = {t: {"n": len(v), "accuracy": _rate(v)} for t, v in sorted(tag_buckets.items())}

    in_tok = sum(r["input_tokens"] for r in records)
    out_tok = sum(r["output_tokens"] for r in records)
    s: dict[str, Any] = {
        "n_questions": len(records),
        "n_answerable": len(answerable),
        "n_refusal": len(refusal),
        "exec_accuracy": exec_acc,
        "first_attempt_accuracy": first_acc,
        "correction_lift": None if exec_acc is None else round(exec_acc - first_acc, 4),
        "refusal_accuracy": _rate([r["correct"] for r in refusal]),
        "by_difficulty": by_diff,
        "by_tag": by_tag,
        "errors": sum(1 for r in records if r["status"] == "error"),
        "avg_seconds": round(mean(r["seconds"] for r in records), 2) if records else None,
        "avg_llm_calls": round(mean(r["llm_calls"] for r in records), 2) if records else None,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "failure_types": dict(Counter(r["failure_type"] for r in records if not r["correct"])),
    }
    if price_in is not None and price_out is not None and records:
        cost = (in_tok * price_in + out_tok * price_out) / 1_000_000
        s["cost_usd"] = round(cost, 4)
        s["cost_per_question_usd"] = round(cost / len(records), 5)
    return s


def aggregate_runs(summaries: list[dict]) -> dict:
    out = {"n_runs": len(summaries)}
    for key in ("exec_accuracy", "first_attempt_accuracy", "correction_lift", "refusal_accuracy"):
        vals = [s[key] for s in summaries if s.get(key) is not None]
        out[key] = ({"mean": round(mean(vals), 4), "min": min(vals), "max": max(vals)} if vals else None)
    return out


def _fmt(agg: dict | None) -> str:
    if not agg:
        return "n/a"
    if agg["min"] == agg["max"]:
        return _pct(agg["mean"])
    return f"{_pct(agg['mean'])} (min {_pct(agg['min'])}, max {_pct(agg['max'])})"


def to_markdown(name: str, config: dict, runs: list[dict], aggregate: dict) -> str:
    first = runs[0]["summary"]
    L = [f"# Evaluation report: {name}", ""]
    L += ["## Configuration", ""] + [f"- **{k}:** {v}" for k, v in config.items()] + [""]
    L += ["## Headline results", "",
          f"Runs: {aggregate['n_runs']} (accuracy shown as mean; range given when runs differ)", "",
          "| Metric | Value |", "|---|---|",
          f"| Execution accuracy (answerable questions, n={first['n_answerable']}) | {_fmt(aggregate['exec_accuracy'])} |",
          f"| First-attempt accuracy | {_fmt(aggregate['first_attempt_accuracy'])} |",
          f"| Self-correction lift | {_fmt(aggregate['correction_lift'])} |",
          f"| Refusal accuracy (unanswerable/unsafe, n={first['n_refusal']}) | {_fmt(aggregate['refusal_accuracy'])} |",
          f"| Avg seconds per question | {first['avg_seconds']} |",
          f"| Avg LLM calls per question | {first['avg_llm_calls']} |",
          f"| Tokens in / out (run 1) | {first['input_tokens']} / {first['output_tokens']} |"]
    if "cost_per_question_usd" in first:
        L.append(f"| Cost per question (USD, run 1) | {first['cost_per_question_usd']} |")
    L.append(f"| API/pipeline errors (run 1) | {first['errors']} |")
    L += ["", "## Accuracy by difficulty (run 1, answerable only)", "", "| Difficulty | n | Accuracy |", "|---|---|---|"]
    for d, v in first["by_difficulty"].items():
        L.append(f"| {d} | {v['n']} | {_pct(v['accuracy'])} |")
    L += ["", "## Failure types (run 1)", ""]
    if first["failure_types"]:
        L += ["| Type | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(first["failure_types"].items(), key=lambda kv: -kv[1])]
    else:
        L.append("No failures.")
    fails = [r for r in runs[0]["records"] if not r["correct"]]
    L += ["", f"## Failed questions (run 1): {len(fails)}", ""]
    for r in fails:
        L += [f"### {r['id']} ({r['difficulty']}, {r['failure_type']})", f"**Question:** {r['question']}", ""]
        if r.get("error"):
            L += [f"**Error:** {str(r['error'])[:300]}", ""]
        if r.get("sql"):
            L += ["Generated SQL:", "```sql", r["sql"], "```"]
        if r.get("gold_sql"):
            L += ["Reference SQL:", "```sql", r["gold_sql"], "```"]
        L.append("")
    L += ["## Notes", "",
          "- Review failures by hand: some may be a reasonable alternative reading, or an error in the reference SQL.",
          "- Free-tier and different models are not comparable; always report which model produced these numbers."]
    return "\n".join(L) + "\n"
