from __future__ import annotations

from typing import Any


def format_prior_results(results: list[dict[str, Any]], max_rows: int = 10, max_chars: int = 3000) -> str:
    """Compact text summary of earlier sub-question results, handed to later sub-questions so
    they can build on them (pick filters/entities such as 'the top category'). Only a preview of
    each result is included, and the whole block is length-capped to protect the context window."""
    if not results:
        return ""
    blocks = []
    for i, r in enumerate(results, 1):
        head = f"SUB-QUESTION {i}: {r['question']}"
        if r.get("status") != "success":
            err = (r.get("error") or "unknown error")[:200]
            blocks.append(f"{head}\nSTATUS: failed ({err})")
            continue
        rows = r.get("rows", [])
        lines = [head, f"SQL: {r.get('sql')}", "COLUMNS: " + " | ".join(r.get("columns", []))]
        lines.append(f"ROWS (first {min(len(rows), max_rows)} of {len(rows)}):")
        lines += [" | ".join(str(v) for v in row) for row in rows[:max_rows]]
        blocks.append("\n".join(lines))
    text = "\n\n".join(blocks)
    return text if len(text) <= max_chars else text[:max_chars] + "\n...(truncated)"
