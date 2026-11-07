"""会话与消息持久化（SQLite），并提供旧 JSON 会话自动迁移。"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from . import config
from .db import db_cursor, get_conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_session_id() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def create_session(nick_name: str, nature: str, persona_id: str | None = None, title: str | None = None) -> str:
    sid = new_session_id()
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO sessions (id, title, persona_id, nick_name, nature, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (sid, title or "新会话", persona_id, nick_name, nature, now, now),
        )
    return sid


def list_sessions() -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute("SELECT * FROM sessions ORDER BY updated_at DESC").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_session(session_id: str) -> dict | None:
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def update_profile(session_id: str, nick_name: str, nature: str, persona_id: str | None = None) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE sessions SET nick_name=?, nature=?, persona_id=?, updated_at=? WHERE id=?",
            (nick_name, nature, persona_id, _now(), session_id),
        )


def rename_session(session_id: str, title: str) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute("UPDATE sessions SET title=?, updated_at=? WHERE id=?", (title, _now(), session_id))


def delete_session(session_id: str) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        cur.execute("DELETE FROM sessions WHERE id=?", (session_id,))


def add_message(session_id: str, role: str, content: str) -> None:
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), session_id, role, content, _now()),
        )
        cur.execute("UPDATE sessions SET updated_at=? WHERE id=?", (_now(), session_id))


def list_messages(session_id: str) -> list[dict]:
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id=? ORDER BY created_at, rowid",
            (session_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def export_markdown(session_id: str) -> str:
    sess = get_session(session_id)
    if not sess:
        return ""
    lines = [f"# 会话：{sess['title']}", f"> 昵称：{sess['nick_name']} ｜ 性格：{sess['nature']}", ""]
    for m in list_messages(session_id):
        speaker = "我" if m["role"] == "user" else sess["nick_name"]
        lines.append(f"**{speaker}**（{m['created_at']}）：\n\n{m['content']}\n")
    return "\n".join(lines)


def migrate_json_file(json_path: Path) -> str | None:
    """把旧版 sessions/*.json 迁移到 SQLite；已存在同名会话则跳过。"""
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[迁移] 跳过 {json_path.name}: {exc}")
        return None
    sid = data.get("current_session") or json_path.stem
    if get_session(sid):
        return sid
    nick = data.get("nick_name", "AI伴侣")
    nature = data.get("nature", "温柔体贴")
    now = _now()
    with db_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO sessions (id, title, persona_id, nick_name, nature, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (sid, sid, None, nick, nature, now, now),
        )
        for msg in data.get("messages", []):
            role = msg.get("role")
            content = msg.get("content")
            if role in ("user", "assistant") and content:
                cur.execute(
                    "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?,?,?,?,?)",
                    (str(uuid.uuid4()), sid, role, content, now),
                )
    return sid


def migrate_all_legacy() -> int:
    legacy = config.LEGACY_SESSION_DIR
    if not legacy.exists():
        return 0
    count = 0
    for jf in sorted(legacy.glob("*.json")):
        if migrate_json_file(jf):
            count += 1
    return count
