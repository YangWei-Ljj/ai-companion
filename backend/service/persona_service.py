"""人格预设：启动时从 presets/presets.json 种子导入（幂等），运行时只读。"""
from __future__ import annotations

from sqlalchemy import text

from backend.core.security import utcnow_iso
from backend.infrastructure.db import get_engine
from app.personas import load_presets


def seed_personas() -> int:
    """把 presets.json 中尚不存在的人格写入 personas 表，返回新导入条数。"""
    presets = load_presets()
    n = 0
    now = utcnow_iso()
    with get_engine().begin() as conn:
        for p in presets:
            exists = conn.execute(
                text("SELECT id FROM personas WHERE id=:i"), {"i": p["id"]}
            ).fetchone()
            if exists:
                continue
            conn.execute(
                text(
                    "INSERT INTO personas(id,name,nick_name,nature,created_at)"
                    " VALUES (:id,:name,:nn,:nature,:ts)"
                ),
                {"id": p["id"], "name": p["name"], "nn": p["nick_name"],
                 "nature": p["nature"], "ts": now},
            )
            n += 1
    return n


def list_personas() -> list[dict]:
    with get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT id,name,nick_name,nature FROM personas ORDER BY rowid")
        ).fetchall()
    return [dict(r._mapping) for r in rows]


def get_persona(persona_id: str | None) -> dict | None:
    if not persona_id:
        return None
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT id,name,nick_name,nature FROM personas WHERE id=:i"),
            {"i": persona_id},
        ).fetchone()
    return dict(row._mapping) if row else None
