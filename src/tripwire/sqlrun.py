"""Run SQL against a SQLite database safely: read-only, with a time limit and a row cap."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunResult:
    rows: list[tuple] | None  # None when the query failed
    error: str | None
    seconds: float
    truncated: bool = False


def run_sql(db: Path | str, sql: str, timeout_s: float = 10.0, max_rows: int = 10_000) -> RunResult:
    """Execute one query read-only. A query that runs past timeout_s is interrupted and reported as an error."""
    start = time.monotonic()
    if str(db) == ":memory:":
        raise ValueError("pass a file path; use run_sql_conn for in-memory databases")
    conn = sqlite3.connect(f"file:{Path(db).resolve()}?mode=ro", uri=True)
    try:
        return run_sql_conn(conn, sql, timeout_s, max_rows, start)
    finally:
        conn.close()


def run_sql_conn(conn: sqlite3.Connection, sql: str, timeout_s: float = 10.0, max_rows: int = 10_000,
                 start: float | None = None) -> RunResult:
    start = time.monotonic() if start is None else start
    deadline = start + timeout_s
    # SQLite calls this every N virtual-machine steps; returning non-zero aborts the query.
    conn.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
    try:
        cur = conn.execute(sql)
        rows = cur.fetchmany(max_rows + 1)
        truncated = len(rows) > max_rows
        return RunResult(rows[:max_rows], None, time.monotonic() - start, truncated)
    except sqlite3.Error as e:
        msg = "timeout" if time.monotonic() > deadline else f"{type(e).__name__}: {e}"
        return RunResult(None, msg, time.monotonic() - start)
    finally:
        conn.set_progress_handler(None, 0)
