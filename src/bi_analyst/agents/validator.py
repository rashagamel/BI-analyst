from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from ..db import Database, SchemaInfo

_FORBIDDEN = tuple(
    getattr(exp, n) for n in
    ("Insert", "Update", "Delete", "Drop", "Create", "Alter", "AlterTable", "Command", "Merge",
     "TruncateTable", "Grant", "Pragma", "Set", "Use", "Copy", "Attach", "Detach")
    if hasattr(exp, n)
)

_SQLGLOT_DIALECT = {"sqlite": "sqlite", "postgresql": "postgres", "mysql": "mysql"}


def validate_sql(sql: str, schema: SchemaInfo, db: Database) -> str | None:
    """Return None if valid, else an error string prefixed with an error type
    (the corrector keys its repair strategy off that prefix)."""
    dialect = _SQLGLOT_DIALECT.get(db.dialect, None)

    # 1. parse (exactly one statement)
    try:
        statements = [s for s in sqlglot.parse(sql, read=dialect) if s is not None]
    except ParseError as e:
        return f"syntax: {e}"
    if len(statements) != 1:
        return "unsafe: multiple statements are not allowed"
    tree = statements[0]

    # 2. read-only
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)) or tree.find(*_FORBIDDEN):
        return "unsafe: only a single read-only SELECT is allowed"

    # 3. tables exist (ignoring CTE names)
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    known = {t.lower() for t in schema.tables}
    for t in tree.find_all(exp.Table):
        if t.name.lower() not in known and t.name.lower() not in ctes:
            return f"unknown_table: table '{t.name}' does not exist. Available: {', '.join(schema.tables)}"

    # 4. columns resolve against the schema (catches hallucinated / mis-attributed columns)
    try:
        qualify(tree.copy(), schema=schema.sqlglot_schema(), dialect=dialect,
                validate_qualify_columns=True, identify=False)
    except OptimizeError as e:
        return f"unknown_column: {e}"
    except Exception as e:  # noqa: BLE001  (sqlglot can raise varied errors on odd SQL)
        return f"syntax: {e}"

    # 5. the database itself accepts it (cheap EXPLAIN, no execution)
    try:
        db.explain(sql)
    except Exception as e:  # noqa: BLE001
        return f"{e.__class__.__name__}: {str(getattr(e, 'orig', e))}"
    return None
