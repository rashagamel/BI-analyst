"""Result-set comparison used to score generated SQL against reference ("gold") SQL."""
from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Sequence


def normalize_cell(v: Any) -> Any:
    """Numbers compare as floats rounded to 2 decimals (5 == 5.0 == 5.004); text is stripped."""
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float, Decimal)):
        return round(float(v), 2)
    return str(v).strip()


def normalize_rows(rows: Sequence[Sequence[Any]]) -> list[tuple]:
    return [tuple(normalize_cell(c) for c in r) for r in rows]


def results_match(gold_rows: Sequence[Sequence[Any]], got_rows: Sequence[Sequence[Any]], ordered: bool = False) -> bool:
    """Same values in the same column order. Row order is ignored unless `ordered`.
    Column NAMES are ignored (aliases differ); an extra or missing column is a mismatch."""
    g, r = normalize_rows(gold_rows), normalize_rows(got_rows)
    return g == r if ordered else Counter(g) == Counter(r)


def mismatch_reason(gold_rows: Sequence[Sequence[Any]], got_rows: Sequence[Sequence[Any]], ordered: bool = False) -> str | None:
    """None if the results match, else one of: empty_result, column_count, row_count, order, values."""
    if results_match(gold_rows, got_rows, ordered):
        return None
    g, r = normalize_rows(gold_rows), normalize_rows(got_rows)
    if not r and g:
        return "empty_result"
    if g and r and len(g[0]) != len(r[0]):
        return "column_count"
    if len(g) != len(r):
        return "row_count"
    if ordered and Counter(g) == Counter(r):
        return "order"
    return "values"
