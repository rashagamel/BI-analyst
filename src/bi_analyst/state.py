from __future__ import annotations

from typing import Any, TypedDict


class AnalystState(TypedDict, total=False):
    """Per-request state. Nothing request-scoped lives in module globals, so
    concurrent requests are safe (a known weakness of some existing repos)."""

    trace_id: str
    question: str
    plan: str
    linked_tables: list[str]
    schema_context: str
    sql: str
    attempts: int
    history: list[dict[str, str]]   # [{sql, error, error_type}] for the corrector
    error: str | None               # error from the latest validate/execute step
    unanswerable: str               # reason, when the writer says the schema cannot answer
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    warnings: list[str]             # data-validation findings
    status: str                     # "success" | "failed" | "unanswerable" | "partial" (multi_step only)
    route: str                      # "simple" | "multi_step"
    sub_questions: list[str]        # router output (== [question] when simple)
    sub_results: list[dict[str, Any]]  # one entry per sub-question (multi_step only)
    primary_index: int              # multi_step: 1-based index of the sub-result mirrored at top level (0 = none)
    prior_context: str              # preview of earlier sub-question results (for dependent sub-questions)
