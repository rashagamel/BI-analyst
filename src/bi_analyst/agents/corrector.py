from __future__ import annotations

import re

# Error type -> repair hint injected into the next SQL-writer prompt. Different failure
# classes need different repairs; a blind "try again" mostly repeats the same mistake.
_PATTERNS = [
    ("unsafe", r"unsafe|read-only|only select|not allowed|forbidden|multiple statements"),
    ("unknown_table", r"unknown_table|no such table|relation .* does not exist|unknown table"),
    ("unknown_column", r"unknown_column|no such column|column .* does not exist|unknown column"),
    ("ambiguous_column", r"ambiguous"),
    ("timeout", r"interrupted|timeout|timed out"),
    ("syntax", r"syntax|parse|unexpected|invalid expression"),
]

HINTS = {
    "unsafe": "Only a single read-only SELECT (CTEs allowed) is permitted. Remove any write/DDL.",
    "unknown_table": "You referenced a table that does not exist. Use ONLY tables from the schema, exactly as spelled.",
    "unknown_column": "You referenced a column that does not exist. Re-read the schema: use only listed columns, "
                      "and check which table each column belongs to (you may need a JOIN).",
    "ambiguous_column": "A column name exists in several joined tables. Qualify every column with its table alias.",
    "timeout": "The query was too expensive. Add filters, avoid cross joins, aggregate earlier.",
    "syntax": "Fix the SQL syntax for the target dialect.",
    "other": "Re-examine the error message and the schema, then produce a corrected query.",
}


def classify(error: str) -> str:
    low = error.lower()
    for kind, pat in _PATTERNS:
        if re.search(pat, low):
            return kind
    return "other"


def repair_context(history: list[dict[str, str]]) -> str:
    if not history:
        return ""
    parts = ["PREVIOUS FAILED ATTEMPTS (do not repeat them):"]
    for i, h in enumerate(history, 1):
        parts.append(f"Attempt {i} SQL:\n{h['sql']}\nError ({h['error_type']}): {h['error']}\n"
                     f"Hint: {HINTS.get(h['error_type'], HINTS['other'])}")
    return "\n\n".join(parts)
