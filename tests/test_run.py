from collections import Counter

from tripwire.cases import Case
from tripwire.judges import Judge
from tripwire.report import bird_rows, summarize
from tripwire.run import INJECTION, case_id, load_done, run, sample, slice_for_slow_judges


def case(qid, kind, op, label, bird_ex=True):
    return Case(qid, "shop", "q", "", "SELECT 1", kind, op, "SELECT 1", label, bird_ex)


CASES = ([case(i, "reference", "reference", "correct") for i in range(50)]
         + [case(i, "equivalent", "swap_and", "correct") for i in range(20)]
         + [case(i, "mutant", "drop_where", "wrong", bird_ex=False) for i in range(20)]
         + [case(i, "mutant", "flip_order", "unclear") for i in range(5)])


def test_sample_is_stratified_repeatable_and_skips_unclear():
    s = sample(CASES, seed=1, refs=10, per_equivalent=5, per_mutant=6, injected=3)
    ops = Counter(c.op for c in s)
    assert ops == {"reference": 10, "swap_and": 5, "drop_where": 6, "drop_where+inject": 3}
    assert all(c.sql.startswith(INJECTION) for c in s if c.op.endswith("+inject"))
    assert [case_id(c) for c in s] == [case_id(c) for c in sample(CASES, seed=1, refs=10, per_equivalent=5,
                                                                   per_mutant=6, injected=3)]


def test_small_slice_keeps_every_operator():
    s = sample(CASES, seed=1, refs=10, per_equivalent=5, per_mutant=6, injected=3)
    assert {c.op for c in slice_for_slow_judges(s, n=8)} == {c.op for c in s}


class SaysCorrect(Judge):
    name = "yes-man"

    def __init__(self):
        self.calls = 0

    def ask(self, prompt):
        self.calls += 1
        return '{"verdict": "correct", "reason": "looks fine"}', 0.001, "test"


def test_run_resumes_and_summary_counts(tmp_path, monkeypatch):
    monkeypatch.setattr("tripwire.run.build_prompt", lambda *a, **k: "prompt")
    s = sample(CASES, seed=1, refs=4, per_equivalent=2, per_mutant=3, injected=2)
    j, out = SaysCorrect(), tmp_path / "j.jsonl"
    rows = run(j, s, {"shop": tmp_path}, out, workers=2)
    assert j.calls == len(s) and len(load_done(out)) == len(s)
    run(j, s, {"shop": tmp_path}, out)            # nothing left to do
    assert j.calls == len(s)
    summary = summarize(rows)
    assert summary["caught_wrong"] == (0, 3) and summary["caught_injected"] == (0, 2)
    assert summary["failed_correct"] == (0, 6)
    assert summarize(bird_rows(rows))["caught_wrong"] == (3, 3)
