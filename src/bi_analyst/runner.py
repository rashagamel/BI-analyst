from __future__ import annotations

import uuid
from typing import Any

from .config import Settings
from .db import Database
from .graph import Deps, build_graph
from .llm import LLM, make_llm
from .tracing import Tracer


class BIAnalyst:
    """Facade: one compiled graph, safe to call concurrently (state is per-call)."""

    def __init__(self, settings: Settings | None = None, llm: LLM | None = None, db: Database | None = None):
        self.settings = settings or Settings()
        self.db = db or Database(self.settings.db_url, self.settings.max_rows, self.settings.query_timeout_s)
        self.llm = llm or make_llm(self.settings)
        self.schema = self.db.schema()
        self.tracer = Tracer(self.settings.trace_dir)
        self._graph = build_graph(Deps(self.llm, self.db, self.schema, self.settings, self.tracer))

    def ask(self, question: str) -> dict[str, Any]:
        trace_id = uuid.uuid4().hex[:12]
        out = self._graph.invoke({"question": question, "trace_id": trace_id})
        return {
            "trace_id": trace_id,
            "status": out.get("status", "failed"),
            "question": question,
            "plan": out.get("plan"),
            "sql": out.get("sql"),
            "attempts": out.get("attempts", 0),
            "columns": out.get("columns", []),
            "rows": out.get("rows", []),
            "warnings": out.get("warnings", []),
            "error": out.get("error"),
            "history": out.get("history", []),
        }
