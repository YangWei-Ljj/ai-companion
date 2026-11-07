"""消息业务：落库 / 历史加载 / 上下文裁剪。"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from backend.core.security import utcnow_iso
from backend.infrastructure.db import get_engine
from app import config as app_config


def add_message(conversation_id: str, role: str, content: str) -> str:
    mid = str(uuid.uuid4())
    now = utcnow_iso()
    with get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO messages(id,conversation_id,role,content,created_at)"
                 " VALUES (:id,:cid,:role,:content,:ts)"),
            {"id": mid, "cid": conversation_id, "role": role,
             "content": content, "ts": now},
        )
        conn.execute(
            text("UPDATE conversations SET updated_at=:ts WHERE id=:cid"),
            {"ts": now, "cid": conversation_id},
        )
    return mid


def list_messages(conversation_id: str) -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id,role,content,created_at FROM messages "
                "WHERE conversation_id=:c ORDER BY created_at, rowid"
            ),
            {"c": conversation_id},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def build_llm_history(conversation_id: str) -> list[dict]:
    """只取 user/assistant 消息，并裁剪最近 N 条，防超窗。"""
    msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in list_messages(conversation_id)
        if m["role"] in ("user", "assistant")
    ]
    max_n = app_config.LLM_MAX_HISTORY_MESSAGES
    return msgs[-max_n:] if len(msgs) > max_n else msgs
