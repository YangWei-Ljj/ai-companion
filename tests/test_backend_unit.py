"""安全原语与迁移幂等性的单元测试（离线）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_password_hash_roundtrip():
    from backend.core import security
    salt, h = security.hash_password("hunter2")
    assert salt and h and salt != h
    assert security.verify_password("hunter2", salt, h) is True
    assert security.verify_password("wrong", salt, h) is False


def test_token_opaque_and_hashed():
    from backend.core import security
    t1 = security.generate_token()
    t2 = security.generate_token()
    assert t1 != t2  # 不透明、不可预测
    th = security.hash_token(t1)
    assert th != t1  # 库里存的是哈希，不是明文


def test_migration_idempotent(tmp_path, monkeypatch):
    """alembic upgrade head 可重复执行不报错（第二次已是 head）。"""
    db_file = tmp_path / "idem.db"
    monkeypatch.setenv("BACKEND_DATABASE_URL", f"sqlite:///{db_file}")
    import backend.infrastructure.db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", str(db_file))
    dbmod.reset_engine()

    from backend.main import run_migrations
    run_migrations()
    run_migrations()  # 第二次幂等
    from sqlalchemy import text
    with dbmod.get_engine().connect() as conn:
        tables = {r[0] for r in conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'"))}
    for t in ("users", "auth_tokens", "personas", "conversations",
              "messages", "background_jobs", "audit_logs"):
        assert t in tables, f"缺表 {t}"
