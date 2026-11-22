"""tripwire build: turn BIRD Mini-Dev into labelled cases and report what BIRD's own grader lets through."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from . import bird
from .cases import build_all, read_jsonl, write_jsonl
from .judges import JUDGES
from .report import load as load_judgements, render
from .run import run, sample, slice_for_slow_judges


def cmd_build(args) -> None:
    questions = bird.load(Path(args.data))
    if args.limit:
        questions = questions[: args.limit]
    def progress(i, n):
        if i % 50 == 0:
            print(f"  {i}/{len(questions)} questions, {n} cases", flush=True)

    all_cases, skipped = build_all(questions, timeout_s=args.timeout, workers=args.workers, progress=progress)
    write_jsonl(all_cases, Path(args.out))

    print(f"\n{len(questions)} questions -> {len(all_cases)} cases, written to {args.out}")
    print("set aside:", dict(skipped) or "none")
    print(f"\n{'operator':<22}{'kind':<12}{'cases':>6}{'BIRD passes':>13}")
    rows = Counter((c.op, c.kind) for c in all_cases if c.kind != "reference")
    passes = Counter((c.op, c.kind) for c in all_cases if c.kind != "reference" and c.bird_ex)
    for (op, kind), n in sorted(rows.items(), key=lambda x: (x[0][1], x[0][0])):
        print(f"{op:<22}{kind:<12}{n:>6}{passes[(op, kind)]:>13}")
    unclear = sum(c.label == "unclear" for c in all_cases)
    print(f"\nunclear (only order or duplicates differ, and the question doesn't clearly ask; needs a human label): {unclear}")
    wrong = [c for c in all_cases if c.label == "wrong"]
    free = sum(c.bird_ex for c in wrong)
    if wrong:
        print(f"\nBIRD's set-based check passed {free} of {len(wrong)} wrong answers ({free / len(wrong):.1%}).")


def cmd_judge(args) -> None:
    cases = sample(read_jsonl(Path(args.cases)), seed=args.seed)
    if args.small:
        cases = slice_for_slow_judges(cases, n=args.small, seed=args.seed)
    judge = JUDGES[args.judge]()
    dbs = {q.db_id: q.db_path for q in bird.load(Path(args.data))}
    out = Path(args.results) / "judgements" / f"{judge.name}.jsonl"
    print(f"{judge.name}: {len(cases)} cases -> {out}", flush=True)

    def progress(done, total, row):
        if done % 10 == 0 or done == total:
            print(f"  {done}/{total}", flush=True)

    run(judge, cases, dbs, out, workers=args.workers, progress=progress)


def cmd_report(args) -> None:
    print(render(load_judgements(Path(args.results))))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="tripwire", description="Test AI graders with look-alike wrong answers.")
    sub = p.add_subparsers(required=True)
    b = sub.add_parser("build", help="build labelled cases from BIRD Mini-Dev")
    b.add_argument("--data", default="data", help="folder holding BIRD Mini-Dev (databases + question file)")
    b.add_argument("--out", default="results/cases.jsonl")
    b.add_argument("--limit", type=int, default=0, help="only the first N questions (0 = all)")
    b.add_argument("--timeout", type=float, default=10.0, help="seconds per query")
    b.add_argument("--workers", type=int, default=4, help="parallel processes")
    b.set_defaults(func=cmd_build)
    j = sub.add_parser("judge", help="grade the fixed sample with one LLM judge")
    j.add_argument("--judge", choices=sorted(JUDGES), required=True)
    j.add_argument("--cases", default="results/cases.jsonl")
    j.add_argument("--data", default="data")
    j.add_argument("--results", default="results")
    j.add_argument("--workers", type=int, default=3)
    j.add_argument("--seed", type=int, default=7)
    j.add_argument("--small", type=int, default=0, help="grade only a smaller slice of N cases (slow judges)")
    j.set_defaults(func=cmd_judge)
    r = sub.add_parser("report", help="summarise all judge results")
    r.add_argument("--results", default="results")
    r.set_defaults(func=cmd_report)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
