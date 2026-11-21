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


def find_root(data_dir: Path) -> Path:
    """The folder that holds mini_dev_sqlite.json, wherever the zip put it."""
    hits = sorted(data_dir.rglob("mini_dev_sqlite.json"))
    if not hits:
        raise FileNotFoundError(f"mini_dev_sqlite.json not found under {data_dir}; unzip BIRD Mini-Dev there first")
    return hits[0].parent


def load(data_dir: Path) -> list[Question]:
    root = find_root(data_dir)
    dbs = {p.stem: p for p in root.rglob("*.sqlite")}
    out = []
    for item in json.loads((root / "mini_dev_sqlite.json").read_text()):
        db = dbs.get(item["db_id"])
        if db is None:
            raise FileNotFoundError(f"database {item['db_id']}.sqlite missing under {root}")
        out.append(Question(int(item["question_id"]), item["db_id"], item["question"], item.get("evidence", ""),
                            item["SQL"], item.get("difficulty", ""), db))
    return out
