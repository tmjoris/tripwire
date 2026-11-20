# Tripwire

Tripwire tests AI graders by slipping them answers that look right but aren't.

Model training and evaluation increasingly depend on automatic graders: code that runs an answer and checks the
result, or an LLM judge that reads it. When a grader passes a wrong answer, every score built on it is wrong too, and
a model trained against it learns to exploit it. Tripwire measures how often that happens.

## How it works

1. Start from correct answers on a public benchmark (BIRD Mini-Dev, text-to-SQL, SQLite).
2. Make **mutants**: small, realistic bugs such as a missing `WHERE`, `SUM` for `COUNT`, a flipped sort, or a live
   date where a fixed one belongs. Some mutants also try **judge injection**, e.g. a `-- verified correct` comment.
3. Make **equivalents**: answers written differently that are still correct, such as reordered joins or renamed
   aliases.
4. Run each grader on all of them: an execution check, and LLM judges from several model families.
5. Report, per grader: how many mutants it caught, how many equivalents it wrongly failed, which injections fooled it,
   and the cost and time per grade. Then try fixes and measure what each one costs.

## Status

Early work. Numbers will be added only once they are measured.

## Related work

- [evalmut](https://github.com/egnaro9/evalmut) applies mutation testing to rule-based eval graders (no LLM judge).
  Tripwire focuses on LLM judges and execution-based SQL graders on a real benchmark.
- BIRD Mini-Dev ([bird-bench/mini_dev](https://github.com/bird-bench/mini_dev)), CC BY-SA 4.0.
