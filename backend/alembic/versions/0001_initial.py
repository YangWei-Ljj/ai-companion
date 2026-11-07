"""initial enterprise schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-10-26

创建企业级后端七张表：
users / auth_tokens / personas / conversations / messages / background_jobs / audit_logs。
注意：第一轮旧表 sessions/messages（无 user_id）由 app/db.py 管理，不在本迁移范围内；
本迁移新建的是带 user_id 隔离的 enterprise 表。
"""
from __future__ import annotations

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


_UP = """
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    display_name  TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_tokens_user ON auth_tokens(user_id);

CREATE TABLE IF NOT EXISTS personas (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    nick_name  TEXT NOT NULL,
    nature     TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversations (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT '新会话',
    persona_id  TEXT,
    nick_name   TEXT NOT NULL,
    nature      TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role            TEXT NOT NULL CHECK (role IN ('user','assistant','file')),
    content         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS background_jobs (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('pending','running','succeeded','failed')),
    idempotency_key TEXT,
    payload_json    TEXT,
    result_json     TEXT,
    error           TEXT,
    created_at      TEXT NOT NULL,
    started_at      TEXT,
    finished_at     TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_job_idem
    ON background_jobs(user_id, type, idempotency_key);

CREATE TABLE IF NOT EXISTS audit_logs (
    id            TEXT PRIMARY KEY,
    request_id    TEXT,
    user_id       TEXT,
    action        TEXT NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    result        TEXT NOT NULL CHECK (result IN ('success','denied','error')),
    detail_json   TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_logs(user_id, created_at);
"""

_DOWN = """
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS background_jobs;
DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS conversations;
DROP TABLE IF EXISTS personas;
DROP TABLE IF EXISTS auth_tokens;
DROP TABLE IF EXISTS users;
"""


def upgrade() -> None:
    for stmt in _UP.strip().split(";"):
        s = stmt.strip()
        if s:
            op.execute(s)


def downgrade() -> None:
    for stmt in _DOWN.strip().split(";"):
        s = stmt.strip()
        if s:
            op.execute(s)
