from __future__ import annotations

import datetime as dt
import decimal
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import create_engine, event, inspect


@dataclass
class ColumnInfo:
    name: str
    type: str
    pk: bool = False


@dataclass
class TableInfo:
    name: str
    columns: list[ColumnInfo]
    fks: list[tuple[list[str], str, list[str]]] = field(default_factory=list)  # (cols, ref_table, ref_cols)
    samples: dict[str, list[Any]] = field(default_factory=dict)  # low-cardinality text values


@dataclass
class SchemaInfo:
    tables: dict[str, TableInfo]

    def sqlglot_schema(self) -> dict[str, dict[str, str]]:
        return {t.name: {c.name: c.type or "TEXT" for c in t.columns} for t in self.tables.values()}

    def render(self, only: list[str] | None = None) -> str:
        """Compact DDL-ish text for the prompt, including FKs and sample values
        (sample values cut down hallucinated filter literals)."""
        out = []
        for name in (only or list(self.tables)):
            t = self.tables[name]
            cols = []
            for c in t.columns:
                s = f"  {c.name} {c.type}" + (" PRIMARY KEY" if c.pk else "")
                if c.name in t.samples:
                    s += f"  -- e.g. {', '.join(repr(v) for v in t.samples[c.name])}"
                cols.append(s)
            for fk_cols, ref_t, ref_cols in t.fks:
                cols.append(f"  FOREIGN KEY ({', '.join(fk_cols)}) REFERENCES {ref_t}({', '.join(ref_cols)})")
            out.append(f"TABLE {name} (\n" + "\n".join(cols) + "\n)")
        return "\n\n".join(out)


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    truncated: bool


def _jsonable(v: Any) -> Any:
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, bytes):
        return f"<{len(v)} bytes>"
    return v


class Database:
    """Read-only access layer. Defence in depth: the validator rejects non-SELECT SQL,
    and the connection itself is read-only too (use a read-only DB role in production)."""

    def __init__(self, url: str, max_rows: int = 500, timeout_s: float = 10.0):
        self.engine = create_engine(url, future=True)
        self.dialect = self.engine.dialect.name
        self.max_rows = max_rows
        self.timeout_s = timeout_s
        if self.dialect == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _read_only(dbapi_conn, _rec):  # noqa: ANN001
                dbapi_conn.execute("PRAGMA query_only = ON")

    # ---- schema ----
    def schema(self, sample_values: bool = True) -> SchemaInfo:
        insp = inspect(self.engine)
        tables: dict[str, TableInfo] = {}
        for name in insp.get_table_names():
            pks = set(insp.get_pk_constraint(name).get("constrained_columns") or [])
            cols = [ColumnInfo(c["name"], str(c["type"]), c["name"] in pks) for c in insp.get_columns(name)]
            fks = [(fk["constrained_columns"], fk["referred_table"], fk["referred_columns"])
                   for fk in insp.get_foreign_keys(name)]
            tables[name] = TableInfo(name, cols, fks)
        info = SchemaInfo(tables)
        if sample_values:
            self._add_samples(info)
        return info

    def _add_samples(self, info: SchemaInfo, max_distinct: int = 8) -> None:
        q = self.engine.dialect.identifier_preparer.quote
        with self.engine.connect() as conn:
            for t in info.tables.values():
                for c in t.columns:
                    if not any(k in c.type.upper() for k in ("CHAR", "TEXT", "STRING")) or c.pk:
                        continue
                    try:
                        rows = conn.exec_driver_sql(
                            f"SELECT DISTINCT {q(c.name)} FROM {q(t.name)} "
                            f"WHERE {q(c.name)} IS NOT NULL LIMIT {max_distinct + 1}"
                        ).fetchall()
                    except Exception:
                        continue
                    if 0 < len(rows) <= max_distinct:  # only low-cardinality columns
                        t.samples[c.name] = [r[0] for r in rows]

    # ---- execution ----
    def explain(self, sql: str) -> None:
        prefix = "EXPLAIN QUERY PLAN " if self.dialect == "sqlite" else "EXPLAIN "
        with self.engine.connect() as conn:
            conn.exec_driver_sql(prefix + sql).fetchall()

    def run(self, sql: str) -> QueryResult:
        with self.engine.connect() as conn:
            raw = None
            if self.dialect == "sqlite":
                raw = conn.connection.driver_connection
                deadline = time.monotonic() + self.timeout_s
                raw.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
            elif self.dialect == "postgresql":
                conn.exec_driver_sql(f"SET LOCAL statement_timeout = {int(self.timeout_s * 1000)}")
            try:
                res = conn.exec_driver_sql(sql)
                cols = list(res.keys())
                fetched = res.fetchmany(self.max_rows + 1)
            finally:
                if raw is not None:
                    raw.set_progress_handler(None, 0)
        truncated = len(fetched) > self.max_rows
        rows = [[_jsonable(v) for v in r] for r in fetched[: self.max_rows]]
        return QueryResult(cols, rows, truncated)
