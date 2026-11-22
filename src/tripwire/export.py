"""tripwire export: write everything the results page shows into one JSON file, straight from the results."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date
from pathlib import Path

from .cases import Case, read_jsonl
from .report import bird_rows, by_op, load, summarize, with_execution
from .run import INJECTIONS, inject
from .sqlrun import run_sql

# How each results file is shown on the page: display name, model family, and what kind of grader it is.
NAMES = {
    "claude-haiku": ("Claude Haiku", "Anthropic", "judge"),
    "copilot-auto": ("Copilot (auto)", "Microsoft / OpenAI", "judge"),
    "ollama-qwen2.5-coder-7b": ("Qwen2.5-Coder 7B", "Alibaba, open model", "judge"),
    "claude-haiku+hardened": ("Claude Haiku, hardened prompt", "Anthropic", "fix"),
    "claude-haiku+data": ("Claude Haiku, sees the data", "Anthropic", "fix"),
}


def _grader(key: str, rows: list[dict], name: str, family: str, kind: str) -> dict:
    s = summarize(rows)
    return {"key": key, "name": name, "family": family, "kind": kind, "caught": s["caught_wrong"],
            "injected": s["caught_injected"], "failedCorrect": s["failed_correct"], "unreadable": s["unreadable"],
            "costUsd": s["cost_usd"], "seconds": round(s["mean_seconds"], 1), "models": s["models"],
            "byMistake": by_op(rows)}


def _preview(db: Path, sql: str, rows: int = 3) -> dict:
    r = run_sql(db, sql, timeout_s=20)
    return {"rows": [list(x) for x in (r.rows or [])[:rows]], "error": r.error}


def export(results: Path, cases_path: Path, db_paths: dict[str, Path], walk_qid: int, out: Path) -> dict:
    cases = read_jsonl(cases_path)
    judges = load(results)
    first = next(iter(judges.values()))
    graders = [_grader("bird", bird_rows(first), "BIRD execution check", "runs the SQL", "execution")]
    for key, rows in judges.items():
        name, family, kind = NAMES.get(key, (key, "", "judge"))
        graders.append(_grader(key, rows, name, family, kind))
        if kind == "judge":
            graders.append(_grader(f"{key}+exec", with_execution(rows), f"{name} AND execution", family, "combined"))

    inj = load(results / "injections") if (results / "injections" / "judgements").exists() else {}
    injections = []
    for key in judges:
        rows = {r["id"]: r for r in judges[key] + inj.get(key, [])}
        for style in INJECTIONS:
            suffix = "+inject" if style == "comment" else f"+inject:{style}"
            pairs = [(rows.get(i.split("+inject")[0]), r) for i, r in rows.items() if i.endswith(suffix)]
            pairs = [(b, r) for b, r in pairs if b is not None]
            if pairs:
                injections.append({
                    "judge": NAMES.get(key, (key,))[0], "trick": style, "text": INJECTIONS[style].strip(),
                    "caught": (sum(r["correct"] is False for _, r in pairs), len(pairs)),
                    "fooled": (sum(b["correct"] is False and r["correct"] is True for b, r in pairs),
                               sum(b["correct"] is False for b, _ in pairs))})

    # One question's journey: every version of it that was graded, with real results and every verdict.
    mine = [c for c in cases if c.qid == walk_qid]
    by_id: dict[str, Case] = {f"{c.qid}:{c.op}": c for c in mine}
    graded_ids = sorted({r["id"] for rows in judges.values() for r in rows if r["id"].startswith(f"{walk_qid}:")})
    versions = []
    for vid in graded_ids:
        base = by_id.get(vid.split("+inject")[0])
        if base is None:
            continue
        c = base if "+inject" not in vid else inject(base, vid.split("+inject")[1].lstrip(":") or "comment")
        verdicts = {"BIRD execution check": c.bird_ex}
        for key, rows in judges.items():
            hit = next((r for r in rows if r["id"] == vid), None)
            if hit is not None:
                verdicts[NAMES.get(key, (key,))[0]] = hit["correct"]
        versions.append({"op": c.op, "label": c.label, "sql": c.sql, "result": _preview(db_paths[c.db_id], c.sql),
                         "verdicts": verdicts})
    q = mine[0]
    import sqlglot
    try:   # the variants were rendered by sqlglot, so diff against the same rendering to highlight only real changes
        normalized = sqlglot.parse_one(q.gold_sql, read="sqlite").sql(dialect="sqlite")
    except sqlglot.errors.ParseError:
        normalized = q.gold_sql
    walkthrough = {"qid": walk_qid, "db": q.db_id, "question": q.question, "evidence": q.evidence,
                   "referenceSql": q.gold_sql, "referenceNormalized": normalized, "referenceResult": _preview(db_paths[q.db_id], q.gold_sql),
                   "versions": versions}

    kinds = Counter(c.kind for c in cases)
    wrong = [c for c in cases if c.label == "wrong"]
    data = {
        "generated": date.today().isoformat(),
        "dataset": {"questions": len({c.qid for c in cases}), "cases": len(cases), "references": kinds["reference"],
                    "equivalents": kinds["equivalent"], "mutants": kinds["mutant"],
                    "unclear": sum(c.label == "unclear" for c in cases)},
        "bird": {"passedWrong": sum(c.bird_ex for c in wrong), "wrong": len(wrong)},
        "sample": dict(Counter("injected" if "+inject" in r["op"] else r["label"] for r in first)),
        "graders": graders, "injections": injections, "walkthrough": walkthrough,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1, default=str))
    return data
