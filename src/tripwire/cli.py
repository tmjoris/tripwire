"""tripwire build: turn BIRD Mini-Dev into labelled cases and report what BIRD's own grader lets through."""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from . import bird
from .cases import build, write_jsonl


def cmd_build(args) -> None:
    questions = bird.load(Path(args.data))
    if args.limit:
        questions = questions[: args.limit]
    all_cases, skipped = [], Counter()
    for i, q in enumerate(questions, 1):
        cases, sk = build(q, timeout_s=args.timeout)
        all_cases += cases
        skipped += sk
        if i % 50 == 0:
            print(f"  {i}/{len(questions)} questions, {len(all_cases)} cases")
    write_jsonl(all_cases, Path(args.out))

    print(f"\n{len(questions)} questions -> {len(all_cases)} cases, written to {args.out}")
    print("set aside:", dict(skipped) or "none")
    print(f"\n{'operator':<22}{'kind':<12}{'cases':>6}{'BIRD passes':>13}")
    rows = Counter((c.op, c.kind) for c in all_cases if c.kind != "reference")
    passes = Counter((c.op, c.kind) for c in all_cases if c.kind != "reference" and c.bird_ex)
    for (op, kind), n in sorted(rows.items(), key=lambda x: (x[0][1], x[0][0])):
        print(f"{op:<22}{kind:<12}{n:>6}{passes[(op, kind)]:>13}")
    wrong = [c for c in all_cases if c.label == "wrong"]
    free = sum(c.bird_ex for c in wrong)
    if wrong:
        print(f"\nBIRD's set-based check passed {free} of {len(wrong)} wrong answers ({free / len(wrong):.1%}).")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="tripwire", description="Test AI graders with look-alike wrong answers.")
    sub = p.add_subparsers(required=True)
    b = sub.add_parser("build", help="build labelled cases from BIRD Mini-Dev")
    b.add_argument("--data", default="data", help="folder holding BIRD Mini-Dev (databases + question file)")
    b.add_argument("--out", default="results/cases.jsonl")
    b.add_argument("--limit", type=int, default=0, help="only the first N questions (0 = all)")
    b.add_argument("--timeout", type=float, default=10.0, help="seconds per query")
    b.set_defaults(func=cmd_build)
    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
