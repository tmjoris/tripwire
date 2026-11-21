import sqlite3

from tripwire.judges import Judge, build_prompt, parse_verdict


def test_parse_verdict_reads_json_inside_other_text():
    reply = 'Copilot Fusion selected X because...\n\n{"verdict": "incorrect", "reason": "missing filter"}\n'
    assert parse_verdict(reply) == (False, "missing filter")
    assert parse_verdict('{"verdict": "Correct", "reason": "ok"}') == (True, "ok")


def test_parse_verdict_returns_none_for_anything_else():
    assert parse_verdict("I think it's fine") == (None, "")
    assert parse_verdict('{"verdict": "maybe"}') == (None, "")
    assert parse_verdict("") == (None, "")


def test_prompt_has_the_schema_and_sql(tmp_path):
    db = tmp_path / "t.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE customer (id INTEGER, name TEXT)")
    conn.commit()
    conn.close()
    p = build_prompt("Who?", "", db, "SELECT name FROM customer")
    assert "CREATE TABLE customer" in p and "SELECT name FROM customer" in p and "Hint: (none)" in p


class Boom(Judge):
    name = "boom"

    def ask(self, prompt):
        raise RuntimeError("network down")


def test_a_failing_judge_is_recorded_not_raised():
    v = Boom().grade("x")
    assert v.correct is None and "network down" in v.reason
