"""实验追踪：SQLite 记录每次评测与进化代际。"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    strategy_path TEXT NOT NULL,
    segment TEXT NOT NULL,
    fitness REAL,
    metrics_json TEXT,
    source TEXT DEFAULT 'manual',
    parent_id TEXT
);
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    strategy_path TEXT,
    failure_type TEXT,
    content TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_ts ON runs(ts DESC);
"""


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def record_run(
    strategy_path: str,
    segment: str,
    fitness: float | None,
    metrics: dict | None,
    source: str = "manual",
    parent_id: str | None = None,
) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO runs (ts, strategy_path, segment, fitness, metrics_json, source, parent_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (time.time(), strategy_path, segment, fitness,
         json.dumps(metrics, ensure_ascii=False) if metrics else None, source, parent_id),
    )
    conn.commit()
    run_id = cur.lastrowid
    conn.close()
    return run_id


def record_lesson(strategy_path: str, failure_type: str, content: str) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO lessons (ts, strategy_path, failure_type, content) VALUES (?, ?, ?, ?)",
        (time.time(), strategy_path, failure_type, content),
    )
    conn.commit()
    lesson_id = cur.lastrowid
    conn.close()
    return lesson_id


def recent_runs(limit: int = 20) -> list[sqlite3.Row]:
    conn = get_conn()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return rows
