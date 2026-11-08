from __future__ import annotations

import re

from ..db import SchemaInfo


def _tokens(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


def link_schema(question: str, schema: SchemaInfo, top_k: int = 6) -> list[str]:
    """Lexical schema linking: score tables by name/column/sample-value overlap with the
    question, then add FK neighbours so joins stay possible. Swap this for embeddings or an
    LLM-based linker later (see AgentSQL / CHESS-style pruning) without touching the graph."""
    q = _tokens(question)
    scores: dict[str, float] = {}
    for t in schema.tables.values():
        s = 3.0 * len(q & _tokens(t.name.replace("_", " ")))
        for c in t.columns:
            s += 1.0 * len(q & _tokens(c.name.replace("_", " ")))
        for vals in t.samples.values():
            s += 2.0 * sum(1 for v in vals if _tokens(str(v)) & q)
        scores[t.name] = s

    ranked = [n for n, s in sorted(scores.items(), key=lambda kv: -kv[1]) if s > 0][:top_k]
    if not ranked:                      # nothing matched -> give the model everything
        return list(schema.tables)

    selected = list(ranked)
    for name in ranked:                 # FK neighbours, both directions
        t = schema.tables[name]
        for _, ref, _ in t.fks:
            if ref in schema.tables and ref not in selected:
                selected.append(ref)
        for other in schema.tables.values():
            if any(ref == name for _, ref, _ in other.fks) and other.name not in selected:
                selected.append(other.name)
    return selected
