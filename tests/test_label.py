import sqlite3

from tripwire.cases import Case
from tripwire.label import label_cases, load_labels


def test_labels_are_saved_and_resumed(tmp_path):
    db = tmp_path / "shop.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE c (name TEXT); INSERT INTO c VALUES ('Amina'), ('Brian');")
    conn.commit()
    conn.close()
    cases = [Case(1, "shop", "Names", "", "SELECT name FROM c ORDER BY name", "mutant", "flip_order",
                  "SELECT name FROM c ORDER BY name DESC", "unclear", True),
             Case(2, "shop", "Names", "", "SELECT name FROM c", "mutant", "drop_distinct",
                  "SELECT name FROM c", "unclear", True)]
    out, shown = tmp_path / "labels.jsonl", []
    answers = iter(["x", "r", "q"])                  # an invalid key is asked again; then right; then quit
    assert label_cases(cases, {"shop": db}, out, ask=lambda _: next(answers), say=shown.append) == 1
    assert load_labels(out) == {"1:flip_order": "correct"}
    assert any("Brian" in s for s in shown)          # both results are shown to the labeller
    answers = iter(["w"])
    label_cases(cases, {"shop": db}, out, ask=lambda _: next(answers), say=shown.append)
    assert load_labels(out) == {"1:flip_order": "correct", "2:drop_distinct": "wrong"}
