import sqlite3

import pytest

from tripwire.compare import is_ordered, set_match, strict_match
from tripwire.mutate import EQUIVALENTS, MUTANTS, apply, variants
from tripwire.sqlrun import run_sql, run_sql_conn


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "shop.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE customer (id INTEGER PRIMARY KEY, name TEXT, city TEXT);
        CREATE TABLE orders (id INTEGER PRIMARY KEY, cid INTEGER, amount REAL);
        INSERT INTO customer VALUES (1,'Amina','Nairobi'),(2,'Brian','Mombasa'),(3,'Chloe','Nairobi'),(4,'Dan','Kisumu');
        INSERT INTO orders VALUES (1,1,50),(2,1,30),(3,2,80),(4,3,10),(5,3,10),(6,2,20);
    """)
    conn.commit()
    conn.close()
    return path


Q = ("SELECT T1.name, SUM(T2.amount) FROM customer AS T1 INNER JOIN orders AS T2 ON T1.id = T2.cid "
     "WHERE T2.amount > 10 AND T1.city = 'Nairobi' GROUP BY T1.name ORDER BY SUM(T2.amount) DESC LIMIT 1")


def rows(db, sql):
    r = run_sql(db, sql)
    assert r.error is None, r.error
    return r.rows


def test_run_sql_is_read_only(db):
    r = run_sql(db, "DELETE FROM orders")
    assert r.rows is None and "readonly" in r.error.lower()


def test_run_sql_times_out():
    conn = sqlite3.connect(":memory:")
    slow = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i+1 FROM n) SELECT count(*) FROM n"
    r = run_sql_conn(conn, slow, timeout_s=0.2)
    assert r.error == "timeout"


def test_set_match_ignores_order_and_duplicates_but_strict_does_not():
    gold, wrong_order, dupes = [(1,), (2,)], [(2,), (1,)], [(1,), (1,), (2,)]
    assert set_match(gold, wrong_order) and set_match(gold, dupes)
    assert not strict_match(gold, wrong_order, ordered=True)
    assert strict_match(gold, wrong_order, ordered=False)
    assert not strict_match(gold, dupes, ordered=False)


def test_is_ordered_only_for_top_level_order_by():
    assert is_ordered("SELECT a FROM t ORDER BY a")
    assert not is_ordered("SELECT a FROM (SELECT a FROM t ORDER BY a)")


# A query per mutant on which its bug shows up in this small dataset.
SHOWS_BUG = {
    "drop_where": "SELECT name FROM customer WHERE city = 'Nairobi' ORDER BY name",
    "swap_aggregate": Q,
    "flip_order": "SELECT name FROM customer ORDER BY name",
    "limit_off_by_one": "SELECT name FROM customer ORDER BY name LIMIT 2",
    "flip_boundary": "SELECT count(*) FROM orders WHERE amount > 20",
    "drop_distinct": "SELECT DISTINCT T1.city FROM customer AS T1 INNER JOIN orders AS T2 ON T1.id = T2.cid",
    "inner_to_left_join": "SELECT T1.name FROM customer AS T1 INNER JOIN orders AS T2 ON T1.id = T2.cid ORDER BY T1.name",
}


@pytest.mark.parametrize("name", MUTANTS)
def test_each_mutant_changes_the_answer_when_it_applies(db, name):
    sql = SHOWS_BUG[name]
    mutated = apply(MUTANTS[name], sql)
    assert mutated is not None, f"{name} did not apply"
    assert not strict_match(rows(db, sql), rows(db, mutated), ordered=is_ordered(sql)), mutated


def test_a_mutant_can_be_accidentally_equivalent_on_the_data(db):
    """Dropping this WHERE changes the query but not its result here, so it must not be counted as a wrong answer.
    This is why every variant is labelled by running it, never by the operator's name."""
    sql = "SELECT DISTINCT T1.city FROM customer AS T1 INNER JOIN orders AS T2 ON T1.id = T2.cid WHERE T2.amount > 10 ORDER BY T1.city"
    mutated = apply(MUTANTS["drop_where"], sql)
    assert mutated != sql
    assert strict_match(rows(db, sql), rows(db, mutated), ordered=True)


@pytest.mark.parametrize("name", EQUIVALENTS)
def test_each_equivalent_keeps_the_answer(db, name):
    equivalent = apply(EQUIVALENTS[name], Q)
    assert equivalent is not None, f"{name} did not apply"
    assert strict_match(rows(db, Q), rows(db, equivalent), ordered=True), equivalent


def test_operators_that_do_not_apply_return_none():
    assert apply(MUTANTS["drop_where"], "SELECT name FROM customer") is None
    assert apply(MUTANTS["limit_off_by_one"], "SELECT name FROM customer") is None
    assert apply(EQUIVALENTS["rename_aliases"], "SELECT name FROM customer") is None


def test_flip_order_passes_bird_set_match_but_fails_strict(db):
    """The finding Tripwire is built to surface: a wrong sort order sails through set comparison."""
    sql = "SELECT name FROM customer ORDER BY name"
    flipped = apply(MUTANTS["flip_order"], sql)
    gold, pred = rows(db, sql), rows(db, flipped)
    assert set_match(gold, pred)
    assert not strict_match(gold, pred, ordered=True)


def test_variants_lists_both_kinds():
    kinds = {k for k, _, _ in variants(Q)}
    assert kinds == {"mutant", "equivalent"}
