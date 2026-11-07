"""会话业务：归属校验（越权 403）+ CRUD。"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from backend.core.exceptions import ForbiddenError, NotFoundError
from backend.core.security import utcnow_iso
from backend.infrastructure.db import get_engine
from backend.service import persona_service

_DEFAULT_NICK = "小柔"
_DEFAULT_NATURE = "温柔体贴、善解人意"


def create_conversation(user_id: str, title: str | None = None,
                        persona_id: str | None = None,
                        nick_name: str | None = None,
                        nature: str | None = None) -> dict:
    p = persona_service.get_persona(persona_id)
    if p:
        nick_name = nick_name or p["nick_name"]
        nature = nature or p["nature"]
    nick_name = (nick_name or _DEFAULT_NICK).strip() or _DEFAULT_NICK
    nature = (nature or _DEFAULT_NATURE).strip() or _DEFAULT_NATURE
    cid = str(uuid.uuid4())
    now = utcnow_iso()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversations(id,user_id,title,persona_id,nick_name,nature,"
                "created_at,updated_at) VALUES (:id,:uid,:title,:pid,:nn,:nature,:ca,:ua)"
            ),
            {"id": cid, "uid": user_id, "title": title or "新会话", "pid": persona_id,
             "nn": nick_name, "nature": nature, "ca": now, "ua": now},
        )
    return get_conversation_for_user(user_id, cid)


def list_conversations(user_id: str) -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id,title,persona_id,nick_name,nature,created_at,updated_at "
                "FROM conversations WHERE user_id=:u ORDER BY updated_at DESC"
            ),
            {"u": user_id},
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def get_conversation_for_user(user_id: str, conversation_id: str) -> dict:
    """取会话并校验归属：不存在→404；存在但属于他人→403。"""
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM conversations WHERE id=:i AND user_id=:u"),
            {"i": conversation_id, "u": user_id},
        ).fetchone()
        if row:
            return dict(row._mapping)
        any_row = conn.execute(
            text("SELECT id FROM conversations WHERE id=:i"), {"i": conversation_id}
        ).fetchone()
    if any_row:
        raise ForbiddenError("该会话不属于当前用户")
    raise NotFoundError("会话不存在")


def update_conversation(user_id: str, conversation_id: str,
                        fields: dict) -> dict:
    conv = get_conversation_for_user(user_id, conversation_id)  # 校验归属
    sets, params = [], {}
    for k in ("title", "persona_id", "nick_name", "nature"):
        if fields.get(k) is not None:
            sets.append(f"{k}=:{k}")
            params[k] = fields[k]
    if not sets:
        return conv
    sets.append("updated_at=:ua")
    params["ua"] = utcnow_iso()
    params["i"] = conversation_id
    with get_engine().begin() as conn:
        conn.execute(
            text(f"UPDATE conversations SET {', '.join(sets)} WHERE id=:i"), params
        )
    return get_conversation_for_user(user_id, conversation_id)


def delete_conversation(user_id: str, conversation_id: str) -> None:
    get_conversation_for_user(user_id, conversation_id)  # 校验归属
    with get_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM conversations WHERE id=:i AND user_id=:u"),
            {"i": conversation_id, "u": user_id},
        )
