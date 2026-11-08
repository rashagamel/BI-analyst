from __future__ import annotations

from ..llm import LLM

SYSTEM = (
    "You are the planning agent of a BI analyst. Given a business question, write a SHORT plan "
    "(2-4 lines): the measure(s), the grouping dimension(s), filters and time ranges, and any "
    "ambiguity you are resolving (state your assumption). Do NOT write SQL."
)


def plan(llm: LLM, question: str) -> str:
    return llm.complete(SYSTEM, f"Question: {question}", agent="planner").strip()
