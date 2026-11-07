"""SQLite 通用助手：WAL 模式 + 外键 + 幂等建表。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from . import config

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    persona_id  TEXT,
    nick_name   TEXT NOT NULL,
    nature      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    session_id  TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('system','user','assistant','file')),
    content     TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
"""


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    # 并发写入冲突时最多等待 5s 再报 database is locked，提升多请求并存下的健壮性
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def db_cursor(commit: bool = False) -> Iterator[sqlite3.Cursor]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db_cursor(commit=True) as cur:
        cur.executescript(SCHEMA_SQL)


if __name__ == "__main__":
    init_db()
    print(f"数据库已初始化：{config.DB_PATH}")
