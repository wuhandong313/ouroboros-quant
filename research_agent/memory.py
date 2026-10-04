"""回测教训库（外循环记忆）：失败回测 → 结构化教训 → FTS5 检索注入 prompt。

这是跨层经验蒸馏闭环（创新点3）的存储端。
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    strategy_path TEXT,
    failure_type TEXT NOT NULL,        # bias/overfit/risk/invalid/other
    content TEXT NOT NULL,             # 一句话教训
    detail TEXT                        # 可选：轨迹摘要
);
CREATE VIRTUAL TABLE IF NOT EXISTS lessons_fts USING fts5(
    content, detail, failure_type, content='lessons', content_rowid='id'
);
CREATE TRIGGER IF NOT EXISTS lessons_ai AFTER INSERT ON lessons BEGIN
    INSERT INTO lessons_fts(rowid, content, detail, failure_type)
    VALUES (new.id, new.content, new.detail, new.failure_type);
END;
CREATE TRIGGER IF NOT EXISTS lessons_ad AFTER DELETE ON lessons BEGIN
    INSERT INTO lessons_fts(lessons_fts, rowid, content, detail, failure_type)
    VALUES ('delete', old.content, old.detail, old.failure_type);
END;
"""

VALID_FAILURE_TYPES = {"bias", "overfit", "risk", "invalid", "other"}


def get_conn(db_path: Path | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.executescript(SCHEMA)
    return conn


def add_lesson(
    failure_type: str,
    content: str,
    strategy_path: str | None = None,
    detail: str | None = None,
) -> int:
    if failure_type not in VALID_FAILURE_TYPES:
        raise ValueError(f"failure_type 必须是 {VALID_FAILURE_TYPES}")
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO lessons (ts, strategy_path, failure_type, content, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        (time.time(), strategy_path, failure_type, content, detail),
    )
    conn.commit()
    lid = cur.lastrowid
    conn.close()
    return lid


def search_lessons(query: str, limit: int = 5) -> list[dict]:
    """FTS5 检索历史教训，供研究员 prompt 注入。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT l.id, l.failure_type, l.content, l.detail, "
        "bm25(lessons_fts) AS rank "
        "FROM lessons_fts f JOIN lessons l ON l.id = f.rowid "
        "WHERE lessons_fts MATCH ? ORDER BY rank LIMIT ?",
        (query, limit),
    ).fetchall()
    conn.close()
    return [
        {"id": r[0], "failure_type": r[1], "content": r[2], "detail": r[3]}
        for r in rows
    ]


def lesson_stats() -> dict[str, int]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT failure_type, COUNT(*) FROM lessons GROUP BY failure_type"
    ).fetchall()
    conn.close()
    return dict(rows)
