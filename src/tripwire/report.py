"""Summarise judge verdicts: what each grader caught, what it wrongly failed, and what the injection did."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


def _rate(hits: int, n: int) -> str:
    return f"{hits}/{n} ({hits / n:.0%})" if n else "-"


def summarize(rows: list[dict]) -> dict:
    wrong = [r for r in rows if r["label"] == "wrong" and not r["op"].endswith("+inject")]
    injected = [r for r in rows if r["op"].endswith("+inject")]
    correct = [r for r in rows if r["label"] == "correct"]
    readable = [r for r in rows if r["correct"] is not None]
    costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
    return {
        "graded": len(rows),
        "unreadable": len(rows) - len(readable),
        "caught_wrong": (sum(r["correct"] is False for r in wrong), len(wrong)),
        "caught_injected": (sum(r["correct"] is False for r in injected), len(injected)),
        "failed_correct": (sum(r["correct"] is False for r in correct), len(correct)),
        "cost_usd": sum(costs) if costs else None,
        "mean_seconds": sum(r["seconds"] for r in rows) / len(rows) if rows else 0,
        "models": sorted({r["model"] for r in rows}),
    }


def bird_rows(rows: list[dict]) -> list[dict]:
    """BIRD's set-based check on the same cases, written as if it were a judge."""
    return [{**r, "correct": r["bird_ex"], "cost_usd": 0.0, "seconds": 0.0, "model": "set comparison"} for r in rows]


def by_op(rows: list[dict]) -> dict[str, tuple[int, int]]:
    out: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["label"] == "wrong":
            out[r["op"]][0] += r["correct"] is False
            out[r["op"]][1] += 1
    return {k: tuple(v) for k, v in sorted(out.items())}


def load(results_dir: Path) -> dict[str, list[dict]]:
    """Latest verdict per case for each judge file in results/judgements/."""
    judges = {}
    for f in sorted((results_dir / "judgements").glob("*.jsonl")):
        latest = {}
        for line in f.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                latest[r["id"]] = r
        judges[f.stem] = list(latest.values())
    return judges


def render(judges: dict[str, list[dict]]) -> str:
    lines = [f"{'grader':<28}{'caught wrong':>16}{'caught injected':>18}{'failed correct':>17}{'unread':>8}"
             f"{'cost $':>9}{'s/grade':>9}"]
    first = next(iter(judges.values()), [])
    for name, rows in [("BIRD set check", bird_rows(first))] + list(judges.items()):
        s = summarize(rows)
        cost = f"{s['cost_usd']:.3f}" if s["cost_usd"] is not None else "n/a"
        lines.append(f"{name:<28}{_rate(*s['caught_wrong']):>16}{_rate(*s['caught_injected']):>18}"
                     f"{_rate(*s['failed_correct']):>17}{s['unreadable']:>8}{cost:>9}{s['mean_seconds']:>9.1f}")
    lines.append("\ncaught per kind of mistake:")
    ops = sorted({op for rows in judges.values() for op in by_op(rows)})
    names = ["BIRD set check"] + list(judges)
    lines.append(f"{'mistake':<26}" + "".join(f"{n[:16]:>18}" for n in names))
    table = {"BIRD set check": by_op(bird_rows(first)), **{n: by_op(r) for n, r in judges.items()}}
    for op in ops:
        lines.append(f"{op:<26}" + "".join(f"{_rate(*table[n].get(op, (0, 0))):>18}" for n in names))
    return "\n".join(lines)
