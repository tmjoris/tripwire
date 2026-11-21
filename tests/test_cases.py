import sqlite3

import pytest

from tripwire.bird import Question
from tripwire.cases import build, read_jsonl, write_jsonl


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "shop.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customer (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
        INSERT INTO customer VALUES (1,'Amina','Nairobi'),(2,'Brian','Mombasa'),(3,'Chloe','Nairobi'),(4,'Dan','Kisumu');
    """)
    conn.commit()
    conn.close()
    return path


def q(db, sql):
    return Question(1, "shop", "Names in Nairobi, A to Z", "", sql, "simple", db)


def test_labels_come_from_running_the_sql(db):
    cases, skipped = build(q(db, "SELECT name FROM customer WHERE city = 'Nairobi' ORDER BY name"))
    by_op = {c.op: c for c in cases}
    assert by_op["reference"].label == "correct"
    assert by_op["drop_where"].label == "wrong"           # all four names instead of two
    assert by_op["flip_order"].label == "wrong"           # Chloe before Amina
    assert by_op["commute_equality"].label == "correct"   # 'Nairobi' = city
    assert not skipped


def test_bird_set_check_passes_a_wrong_sort_order(db):
    cases, _ = build(q(db, "SELECT name FROM customer WHERE city = 'Nairobi' ORDER BY name"))
    flipped = next(c for c in cases if c.op == "flip_order")
    assert flipped.label == "wrong" and flipped.bird_ex      # a free pass for BIRD's grader
    dropped = next(c for c in cases if c.op == "drop_where")
    assert dropped.label == "wrong" and not dropped.bird_ex  # caught


def test_a_mutant_with_the_same_rows_is_set_aside(db):
    # Every customer is in one of these cities, so the filter changes nothing.
    cases, skipped = build(q(db, "SELECT count(*) FROM customer WHERE city IN ('Nairobi', 'Mombasa', 'Kisumu')"))
    assert "drop_where" not in {c.op for c in cases}
    assert skipped["mutant_same_result"] == 1


def test_a_broken_reference_yields_nothing(db):
    cases, skipped = build(q(db, "SELECT nope FROM customer"))
    assert cases == [] and skipped["reference_failed"] == 1


def test_jsonl_round_trip(db, tmp_path):
    cases, _ = build(q(db, "SELECT name FROM customer ORDER BY name"))
    path = tmp_path / "cases.jsonl"
    write_jsonl(cases, path)
    assert read_jsonl(path) == cases
