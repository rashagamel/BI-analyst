from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable


def _trim(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: (_trim(v[:5]) if k == "rows" and isinstance(v, list) else _trim(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_trim(v) for v in obj]
    return obj


class Tracer:
    """One JSONL file per request: grep-able, diff-able, easy to turn into eval data."""

    def __init__(self, trace_dir: str | None):
        self._dir = Path(trace_dir) if trace_dir else None
        if self._dir:
            self._dir.mkdir(parents=True, exist_ok=True)

    def emit(self, trace_id: str, node: str, data: dict[str, Any]) -> None:
        if not self._dir:
            return
        line = json.dumps({"ts": time.time(), "node": node, **_trim(data)}, default=str)
        with open(self._dir / f"{trace_id}.jsonl", "a", encoding="utf-8") as f:
            f.write(line + "\n")

    def wrap(self, name: str, fn: Callable[[dict], dict]) -> Callable[[dict], dict]:
        def wrapper(state: dict) -> dict:
            t0 = time.perf_counter()
            update = fn(state)
            self.emit(state.get("trace_id", "no-trace"), name,
                      {"ms": round((time.perf_counter() - t0) * 1000, 1), "update": update})
            return update

        return wrapper
