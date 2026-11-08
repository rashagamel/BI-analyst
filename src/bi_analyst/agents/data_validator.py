from __future__ import annotations

from typing import Any

_NON_NEGATIVE_HINTS = ("revenue", "amount", "price", "total", "quantity", "count", "sales")


def check_results(columns: list[str], rows: list[list[Any]], truncated: bool) -> list[str]:
    """Phase-3 starter: cheap, deterministic sanity checks on RESULTS (not SQL).
    Extend with join-explosion detection, % bounds, LLM answer-relevance check, etc."""
    warnings: list[str] = []
    if not rows:
        warnings.append("Query returned no rows - the filter may be too strict or the data may not exist.")
        return warnings
    if truncated:
        warnings.append("Result was truncated at the row limit; aggregates over it may be incomplete.")
    for i, col in enumerate(columns):
        vals = [r[i] for r in rows]
        if all(v is None for v in vals):
            warnings.append(f"Column '{col}' is entirely NULL (possible bad join or wrong column).")
            continue
        nums = [v for v in vals if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums and any(h in col.lower() for h in _NON_NEGATIVE_HINTS) and min(nums) < 0:
            warnings.append(f"Column '{col}' contains negative values, which is unusual for this metric.")
        if nums and ("pct" in col.lower() or "percent" in col.lower()) and max(nums) > 100:
            warnings.append(f"Column '{col}' looks like a percentage but exceeds 100.")
    return warnings
