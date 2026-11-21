"""Ways to decide whether two query results are "the same".

`set_match` is the rule BIRD's execution accuracy uses: compare the results as sets. It ignores row order and
duplicate rows, so it can pass an answer that sorts the wrong way or drops DISTINCT.

`strict_match` is Tripwire's ground truth: rows must match as a multiset, and in order when the reference query
sorts its output (ORDER BY at the top level).
"""

from __future__ import annotations

from collections import Counter

import sqlglot
from sqlglot import exp


def _norm(v):
    # Floats from different but equivalent queries can differ in the last bits (e.g. SUM in a different order).
    return round(v, 9) if isinstance(v, float) else v


def _norm_rows(rows: list[tuple]) -> list[tuple]:
    return [tuple(_norm(v) for v in r) for r in rows]


def set_match(gold: list[tuple], pred: list[tuple]) -> bool:
    return set(gold) == set(pred)


def is_ordered(sql: str) -> bool:
    """True when the outermost query has ORDER BY, so row order is part of the answer."""
    try:
        root = sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return False
    return root.args.get("order") is not None


def strict_match(gold: list[tuple], pred: list[tuple], ordered: bool) -> bool:
    g, p = _norm_rows(gold), _norm_rows(pred)
    return g == p if ordered else Counter(g) == Counter(p)
