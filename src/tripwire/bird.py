"""Load BIRD Mini-Dev (SQLite): questions, their reference SQL, and the database each one runs on."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Question:
    qid: int
    db_id: str
    question: str
    evidence: str  # BIRD's "external knowledge" hint for the question
    sql: str
    difficulty: str
    db_path: Path


def find_questions(data_dir: Path) -> Path:
    """The question file: BIRD's 2026 corrected .jsonl if present, else the 2024 .json from the zip."""
    for pattern in ("mini_dev_sqlite.jsonl", "mini_dev_sqlite.json"):
        hits = sorted(data_dir.rglob(pattern))
        if hits:
            return hits[0]
    raise FileNotFoundError(f"no mini_dev_sqlite.jsonl/.json under {data_dir}; download BIRD Mini-Dev there first")


def load(data_dir: Path) -> list[Question]:
    qfile = find_questions(data_dir)
    dbs = {p.stem: p for p in data_dir.rglob("*.sqlite")}
    text = qfile.read_text()
    items = [json.loads(l) for l in text.splitlines() if l.strip()] if qfile.suffix == ".jsonl" else json.loads(text)
    out = []
    for item in items:
        db = dbs.get(item["db_id"])
        if db is None:
            raise FileNotFoundError(f"database {item['db_id']}.sqlite missing under {data_dir}")
        out.append(Question(int(item["question_id"]), item["db_id"], item["question"], item.get("evidence", ""),
                            item["SQL"], item.get("difficulty", ""), db))
    return out
