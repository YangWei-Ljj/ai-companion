"""数据库连接（SQLAlchemy 2.x + sqlite3）。

- WAL 模式 + 外键 + busy_timeout，与第一轮一致；
- 表结构由 Alembic 迁移管理（先迁移建表，再写业务）；
- ``DB_PATH`` 可在测试中被 monkeypatch 后调用 ``reset_engine()`` 重定向。
"""
from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from backend.core.config import settings

DB_PATH: str = settings.DB_PATH
_engine: Engine | None = None


def _attach_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_conn, _):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        url = f"sqlite:///{DB_PATH}"
        _engine = create_engine(
            url, connect_args={"check_same_thread": False}, future=True
        )
        _attach_pragmas(_engine)
    return _engine


def reset_engine() -> None:
    """测试用：丢弃已缓存 engine，使下一次 get_engine() 用新 DB_PATH 重建。"""
    global _engine
    _engine = None
