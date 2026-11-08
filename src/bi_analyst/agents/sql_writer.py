from __future__ import annotations

import re

from ..llm import LLM
from .corrector import repair_context

SYSTEM = (
    "You are the SQL-writing agent of a BI analyst. Write ONE read-only {dialect} SELECT query "
    "(CTEs allowed) that answers the question using ONLY the tables and columns in the schema. "
    "Rules: never invent columns; qualify columns with table aliases when joining; "
    "exclude cancelled/refunded business records only if the question implies it; "
    "return only the columns needed. Output the SQL in a single ```sql fenced block and nothing else."
)


def extract_sql(text: str) -> str:
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.S | re.I)
    return (m.group(1) if m else text).strip().rstrip(";").strip()


def write_sql(llm: LLM, *, dialect: str, question: str, plan: str, schema_context: str,
              history: list[dict[str, str]]) -> str:
    user = (f"SCHEMA:\n{schema_context}\n\nQUESTION: {question}\n\nPLAN:\n{plan}\n\n"
            f"{repair_context(history)}")
    return extract_sql(llm.complete(SYSTEM.format(dialect=dialect), user, agent="sql_writer"))
