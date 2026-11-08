from __future__ import annotations

from ..db import Database, QueryResult


def execute_sql(db: Database, sql: str) -> QueryResult:
    return db.run(sql)
