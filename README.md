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

## First result: BIRD's own grader

BIRD scores text-to-SQL answers by running them and comparing the result with the reference result **as sets**. Sets
ignore row order and duplicate rows. On all 500 BIRD Mini-Dev questions (2026 corrected set, SQLite):

- Tripwire built **3,012 cases**: 496 reference answers, 1,623 equivalents and 893 mutants.
- Every case is labelled by running it. A mutant only counts as wrong if its rows really differ; if only the order
  or the duplicates differ, it counts as wrong only when the question asks for an order or for distinct values.
  The other **70** are marked *unclear* and wait for a human label.
- **BIRD's set comparison passed 57 of 823 wrong answers (6.9%)**: wrong sort orders on questions that ask for
  an order, and duplicate rows on questions that ask for distinct values. It never failed a correct equivalent.

| Mutant | Cases | Passed by BIRD's check |
|---|---:|---:|
| Sort order reversed | 141 | 116 (incl. 63 unclear) |
| `DISTINCT` dropped | 12 | 11 (incl. 7 unclear) |
| `WHERE` dropped | 352 | 0 |
| Wrong aggregate | 252 | 0 |
| Boundary `>`/`>=` flipped | 87 | 0 |
| `LIMIT` off by one | 26 | 0 |
| `INNER` → `LEFT JOIN` | 23 | 0 |

Next: the same cases through LLM judges from several model families.

## Try it

```
uv run tripwire build --data data --workers 4 --timeout 20   # needs BIRD Mini-Dev under data/
uv run pytest
```

## Data

BIRD Mini-Dev ([bird-bench/mini_dev](https://github.com/bird-bench/mini_dev)), CC BY-SA 4.0.
