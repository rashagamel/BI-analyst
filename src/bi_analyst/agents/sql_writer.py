from __future__ import annotations

import re

from ..llm import LLM
from .corrector import repair_context

SYSTEM = (
    "You are the SQL-writing agent of a BI analyst. Write ONE read-only {dialect} SELECT query "
    "(CTEs allowed) that answers the question using ONLY the tables and columns in the schema. "
    "Rules: never invent tables or columns; qualify columns with table aliases when joining; "
    "apply status or category filters (for example excluding cancelled, refunded or inactive "
    "records) only when the question states or clearly implies them; return only the columns "
    "needed. Output the SQL in a single ```sql fenced block and nothing else. "
    "If the schema does not contain the data needed to answer (a column, table or concept that "
    "does not exist), do NOT guess: reply with one line instead of SQL: CANNOT_ANSWER: <short reason>."
)

CANNOT = "CANNOT_ANSWER"

EARLIER_NOTE = (
    "EARLIER RESULTS from previous steps of the same multi-part question. Use them to choose "
    "filters or entities (for example 'the top category'), but your query must still be a single "
    "read-only SELECT over the schema tables above. Never reference these results as tables."
)


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";").strip()


def is_cannot_answer(sql: str) -> bool:
    return sql.strip().upper().startswith(CANNOT)


def cannot_answer_reason(sql: str) -> str:
    reason = sql.strip()[len(CANNOT):].lstrip(" :-").strip()
    return reason or "the data needed is not in the schema"


def write_sql(llm: LLM, *, dialect: str, question: str, plan: str, schema_context: str,
              history: list[dict[str, str]], context: str = "") -> str:
    earlier = f"{EARLIER_NOTE}\n{context}\n\n" if context else ""
    user = (f"SCHEMA:\n{schema_context}\n\n{earlier}QUESTION: {question}\n\nPLAN:\n{plan}\n\n"
            f"{repair_context(history)}")
    return extract_sql(llm.complete(SYSTEM.format(dialect=dialect), user, agent="sql_writer"))
