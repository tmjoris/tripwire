"""Make look-alike variants of a correct SQL query.

Mutants are small, realistic bugs: each should change the answer. Equivalents are rewrites that should not.
Whether a variant really is wrong (or really is equivalent) is decided later by running it, not assumed here.
Every operator returns the new SQL, or None when it does not apply to this query.
"""

from __future__ import annotations

from typing import Callable

import sqlglot
from sqlglot import exp

Operator = Callable[[exp.Expression], exp.Expression | None]


def _parse(sql: str) -> exp.Expression | None:
    try:
        return sqlglot.parse_one(sql, read="sqlite")
    except sqlglot.errors.ParseError:
        return None


def _render(tree: exp.Expression) -> str:
    return tree.sql(dialect="sqlite")


def _first_in_where(tree: exp.Expression, *types):
    where = tree.find(exp.Where)
    return where.find(*types) if where else None


# ---------------------------------------------------------------- mutants


def drop_where(tree):
    """Forget the filter: the outermost WHERE disappears."""
    if tree.args.get("where") is None:
        return None
    tree.set("where", None)
    return tree


_AGG_SWAP = {exp.Sum: exp.Avg, exp.Avg: exp.Sum, exp.Max: exp.Min, exp.Min: exp.Max}


def swap_aggregate(tree):
    """Use the wrong aggregate: SUM<->AVG, MAX<->MIN."""
    node = tree.find(*_AGG_SWAP)
    if node is None:
        return None
    node.replace(_AGG_SWAP[type(node)](this=node.this.copy()))
    return tree


def flip_order(tree):
    """Sort the wrong way: ASC<->DESC on the first ORDER BY key."""
    order = tree.args.get("order")
    if order is None or not order.expressions:
        return None
    key = order.expressions[0]
    key.set("desc", not key.args.get("desc"))
    return tree


def limit_off_by_one(tree):
    """Return one row too many."""
    limit = tree.args.get("limit")
    if limit is None or not isinstance(limit.expression, exp.Literal) or not limit.expression.is_int:
        return None
    limit.set("expression", exp.Literal.number(int(limit.expression.this) + 1))
    return tree


_CMP_FLIP = {exp.GT: exp.GTE, exp.GTE: exp.GT, exp.LT: exp.LTE, exp.LTE: exp.LT}


def flip_boundary(tree):
    """Get the boundary wrong in the filter: > vs >=, < vs <=."""
    node = _first_in_where(tree, *_CMP_FLIP)
    if node is None:
        return None
    node.replace(_CMP_FLIP[type(node)](this=node.this.copy(), expression=node.expression.copy()))
    return tree


def drop_distinct(tree):
    """Forget DISTINCT, so duplicates come back."""
    if not isinstance(tree, exp.Select) or tree.args.get("distinct") is None:
        return None
    tree.set("distinct", None)
    return tree


def inner_to_left_join(tree):
    """Keep unmatched rows: INNER JOIN becomes LEFT JOIN."""
    for join in tree.find_all(exp.Join):
        if join.args.get("side") is None and (join.args.get("kind") or "INNER").upper() == "INNER":
            join.set("kind", None)
            join.set("side", "LEFT")
            return tree
    return None


MUTANTS: dict[str, Operator] = {
    "drop_where": drop_where,
    "swap_aggregate": swap_aggregate,
    "flip_order": flip_order,
    "limit_off_by_one": limit_off_by_one,
    "flip_boundary": flip_boundary,
    "drop_distinct": drop_distinct,
    "inner_to_left_join": inner_to_left_join,
}

# ---------------------------------------------------------------- equivalents


def rename_aliases(tree):
    """Rename table aliases (T1 -> t_1): same query, different spelling."""
    aliases = {a.this.name: f"t_{i}" for i, a in enumerate(tree.find_all(exp.TableAlias), 1) if a.this}
    if not aliases:
        return None
    for a in tree.find_all(exp.TableAlias):
        if a.this and a.this.name in aliases:
            a.set("this", exp.to_identifier(aliases[a.this.name]))
    for col in tree.find_all(exp.Column):
        if col.table in aliases:
            col.set("table", exp.to_identifier(aliases[col.table]))
    return tree


def swap_and(tree):
    """Swap the two sides of the first AND in the filter."""
    node = _first_in_where(tree, exp.And)
    if node is None:
        return None
    node.replace(exp.And(this=node.expression.copy(), expression=node.this.copy()))
    return tree


def commute_equality(tree):
    """Write a = b as b = a in the filter."""
    node = _first_in_where(tree, exp.EQ)
    if node is None:
        return None
    node.replace(exp.EQ(this=node.expression.copy(), expression=node.this.copy()))
    return tree


def redundant_true(tree):
    """Add a condition that is always true."""
    if not isinstance(tree, exp.Select):
        return None
    true = exp.EQ(this=exp.Literal.number(1), expression=exp.Literal.number(1))
    where = tree.args.get("where")
    tree.set("where", exp.Where(this=exp.And(this=where.this.copy(), expression=true) if where else true))
    return tree


EQUIVALENTS: dict[str, Operator] = {
    "rename_aliases": rename_aliases,
    "swap_and": swap_and,
    "commute_equality": commute_equality,
    "redundant_true": redundant_true,
}


def apply(op: Operator, sql: str) -> str | None:
    """Apply one operator to a copy of the query. None if it doesn't apply or changes nothing."""
    tree = _parse(sql)
    if tree is None:
        return None
    original = _render(tree)
    out = op(tree.copy())
    if out is None:
        return None
    new = _render(out)
    return None if new == original else new


def variants(sql: str) -> list[tuple[str, str, str]]:
    """Every applicable (kind, operator, sql) for one query; kind is "mutant" or "equivalent"."""
    out = []
    for kind, ops in (("mutant", MUTANTS), ("equivalent", EQUIVALENTS)):
        for name, op in ops.items():
            new = apply(op, sql)
            if new is not None:
                out.append((kind, name, new))
    return out
