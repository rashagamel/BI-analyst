from __future__ import annotations

from ..llm import LLM

SYSTEM = (
    "You are the planning agent of a BI analyst. Given a business question, write a SHORT plan "
    "(2-4 lines): the measure(s), the grouping dimension(s), filters and time ranges, and any "
    "ambiguity you are resolving (state your assumption). Do NOT write SQL. "
    "If EARLIER RESULTS are provided, they come from previous steps of the same multi-part "
    "question: use them where the question refers to them."
)


def plan(llm: LLM, question: str, context: str = "") -> str:
    user = f"Question: {question}"
    if context:
        user += f"\n\nEARLIER RESULTS:\n{context}"
    return llm.complete(SYSTEM, user, agent="planner").strip()
