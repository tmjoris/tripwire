"""tripwire label: a person decides the cases the rules could not ("unclear"), one at a time, in the terminal."""

from __future__ import annotations

import json
from pathlib import Path

from .cases import Case
from .sqlrun import run_sql


def _show_rows(rows: list[tuple] | None, limit: int = 8) -> str:
    if rows is None:
        return "  (query failed)"
    lines = [f"  {r}" for r in rows[:limit]]
    if len(rows) > limit:
        lines.append(f"  ... {len(rows) - limit} more rows")
    return "\n".join(lines) or "  (no rows)"


def load_labels(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return {r["id"]: r["label"] for r in map(json.loads, path.read_text().splitlines()) if r.get("label")}


def label_cases(cases: list[Case], db_paths: dict[str, Path], out: Path, ask=input, say=print) -> int:
    """Ask about each case not labelled yet. Returns how many were labelled in this session."""
    done = load_labels(out)
    todo = [c for c in cases if f"{c.qid}:{c.op}" not in done]
    say(f"{len(done)} already labelled, {len(todo)} to go. Answer r (right), w (wrong), s (skip) or q (quit).\n")
    n = 0
    for i, c in enumerate(todo, 1):
        gold = run_sql(db_paths[c.db_id], c.gold_sql).rows
        theirs = run_sql(db_paths[c.db_id], c.sql).rows
        say(f"--- {i}/{len(todo)}  question {c.qid} ({c.db_id}), change: {c.op}\n")
        say(f"QUESTION: {c.question}\n" + (f"HINT: {c.evidence}\n" if c.evidence else ""))
        say(f"REFERENCE SQL:\n  {c.gold_sql}\nREFERENCE RESULT:\n{_show_rows(gold)}\n")
        say(f"CANDIDATE SQL:\n  {c.sql}\nCANDIDATE RESULT:\n{_show_rows(theirs)}\n")
        while (a := ask("Does the candidate answer the question? [r/w/s/q] ").strip().lower()) not in "rwsq" or not a:
            pass
        if a == "q":
            break
        if a == "s":
            continue
        with out.open("a") as f:
            f.write(json.dumps({"id": f"{c.qid}:{c.op}", "label": "correct" if a == "r" else "wrong"}) + "\n")
        n += 1
    say(f"\nLabelled {n} this time, saved to {out}.")
    return n
