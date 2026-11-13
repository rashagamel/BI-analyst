from __future__ import annotations

import json
import re

from ..llm import LLM

SYSTEM = """You are the routing agent of a BI analyst. Decide whether a business question can be \
answered by ONE SQL query ("simple") or needs SEVERAL separate queries ("multi_step").

Default to "simple". Use "multi_step" only when the question clearly asks for several separate \
result sets (for example two unrelated metrics, or "X, and also Y"). A comparison, ranking, \
filter or join that one query can handle is "simple".

For "multi_step", write 2-4 sub-questions in the order they should run. A later sub-question \
may build on an earlier one: it will be given a preview of the earlier results, so say so in \
plain words (for example "for the category with the highest revenue in the previous step"). \
Each sub-question must still be answerable by ONE SQL query on the database.

Reply with JSON only, no other text:
{"route": "simple" | "multi_step", "sub_questions": ["...", "..."]}
For "simple" use an empty list for sub_questions."""


def parse_route(text: str, question: str, max_sub: int = 4) -> tuple[str, list[str]]:
    """Parse the router's reply. ANY problem falls back to the simple path, so a bad
    router answer can never make a question fail that the plain pipeline could answer."""
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return "simple", [question]
    try:
        data = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return "simple", [question]
    if not isinstance(data, dict):
        return "simple", [question]
    subs = data.get("sub_questions") or []
    subs = [x.strip() for x in subs if isinstance(x, str) and x.strip()][:max_sub]
    if data.get("route") == "multi_step" and len(subs) >= 2:
        return "multi_step", subs
    return "simple", [question]


def route_question(llm: LLM, question: str, table_names: list[str], max_sub: int = 4) -> tuple[str, list[str]]:
    user = f"Available tables: {', '.join(table_names)}\n\nQuestion: {question}"
    return parse_route(llm.complete(SYSTEM, user, agent="router"), question, max_sub)
