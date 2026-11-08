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
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool
    warnings: list[str]             # data-validation findings
    status: str                     # "success" | "failed"
