"""Build labelled test cases: the reference answer, its mutants and its equivalents, each labelled by running it.

A mutant is labelled "wrong" only if its result really differs from the reference. Order counts only for
flip_order, the one operator whose bug *is* the order; for the others, a different tie order is not a bug.
An equivalent is labelled "correct" only if its result matches exactly. Everything else is set aside and counted,
because a variant that looks wrong but returns the right rows is not a wrong answer.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from .bird import Question
from .compare import is_ordered, set_match, strict_match
from .mutate import variants
from .sqlrun import run_sql

ORDER_BUGS = {"flip_order"}


@dataclass
class Case:
    qid: int
    db_id: str
    question: str
    evidence: str
    gold_sql: str
    kind: str          # "reference", "mutant" or "equivalent"
    op: str
    sql: str
    label: str         # "correct" or "wrong" (ground truth)
    bird_ex: bool      # would BIRD's set-based execution check pass it?


def build(q: Question, timeout_s: float = 10.0) -> tuple[list[Case], Counter]:
    """All cases for one question, plus counts of what was set aside and why."""
    skipped: Counter = Counter()
    gold = run_sql(q.db_path, q.sql, timeout_s)
    if gold.error or gold.truncated:
        skipped["reference_failed"] += 1
        return [], skipped
    ordered = is_ordered(q.sql)
    base = dict(qid=q.qid, db_id=q.db_id, question=q.question, evidence=q.evidence, gold_sql=q.sql)
    cases = [Case(**base, kind="reference", op="reference", sql=q.sql, label="correct", bird_ex=True)]
    for kind, op, sql in variants(q.sql):
        r = run_sql(q.db_path, sql, timeout_s)
        if r.error or r.truncated:
            skipped[f"{kind}_failed_to_run"] += 1      # a crash is caught by any grader that runs the SQL
            continue
        same_rows = strict_match(gold.rows, r.rows, ordered=False)
        same_order = strict_match(gold.rows, r.rows, ordered=ordered)
        if kind == "equivalent":
            if not same_order:
                skipped["equivalent_changed_result"] += 1
                continue
            label = "correct"
        else:
            differs = not same_rows or (op in ORDER_BUGS and ordered and not same_order)
            if not differs:
                skipped["mutant_same_result"] += 1
                continue
            label = "wrong"
        cases.append(Case(**base, kind=kind, op=op, sql=sql, label=label, bird_ex=set_match(gold.rows, r.rows)))
    return cases, skipped


def write_jsonl(cases: list[Case], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for c in cases:
            f.write(json.dumps(asdict(c)) + "\n")


def read_jsonl(path: Path) -> list[Case]:
    return [Case(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
