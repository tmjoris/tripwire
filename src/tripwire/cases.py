"""Build labelled test cases: the reference answer, its mutants and its equivalents, each labelled by running it.

A mutant is labelled "wrong" only if its result really differs from the reference. Order counts only for
flip_order, the one operator whose bug *is* the order; for the others, a different tie order is not a bug.
An equivalent is labelled "correct" only if its result matches exactly. Everything else is set aside and counted,
because a variant that looks wrong but returns the right rows is not a wrong answer.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

from .bird import Question
from .compare import is_ordered, set_match, strict_match
from .mutate import variants
from .sqlrun import run_sql

ORDER_BUGS = {"flip_order"}

# A reversed order is only a wrong answer if the question asks for an order. Without one of these words the case is
# labelled "unclear" and left out of scores until a person labels it.
ASKS_FOR_ORDER = re.compile(
    r"\b(descend|ascend|order|sort|rank|alphabetical|chronolog|respectively|highest to|lowest to|a to z|z to a|"
    r"from (the )?(highest|lowest|largest|smallest|most|least|top|earliest|latest|oldest|newest))", re.I)
# Likewise, extra duplicate rows are only wrong if the question asks for distinct values.
ASKS_FOR_DISTINCT = re.compile(r"\b(distinct|unique|different|no duplicates?|without duplicates?)\b", re.I)


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
    label: str         # "correct", "wrong" or "unclear" (ground truth; "unclear" waits for a human label)
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
            if not same_rows and set_match(gold.rows, r.rows):     # same values, only duplicates differ
                label = "wrong" if ASKS_FOR_DISTINCT.search(q.question) else "unclear"
            elif not same_rows:
                label = "wrong"
            elif op in ORDER_BUGS and ordered and not same_order:
                label = "wrong" if ASKS_FOR_ORDER.search(q.question) else "unclear"
            else:
                skipped["mutant_same_result"] += 1
                continue
        cases.append(Case(**base, kind=kind, op=op, sql=sql, label=label, bird_ex=set_match(gold.rows, r.rows)))
    return cases, skipped


def _build_one(args):
    q, timeout_s = args
    return build(q, timeout_s)


def build_all(questions: list[Question], timeout_s: float = 10.0, workers: int = 4, progress=None):
    """Build every question's cases in parallel processes (SQLite does the work, so threads would not help)."""
    all_cases, skipped = [], Counter()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, (cases, sk) in enumerate(pool.map(_build_one, [(q, timeout_s) for q in questions]), 1):
            all_cases += cases
            skipped += sk
            if progress:
                progress(i, len(all_cases))
    return all_cases, skipped


def write_jsonl(cases: list[Case], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for c in cases:
            f.write(json.dumps(asdict(c)) + "\n")


def read_jsonl(path: Path) -> list[Case]:
    return [Case(**json.loads(line)) for line in path.read_text().splitlines() if line.strip()]
