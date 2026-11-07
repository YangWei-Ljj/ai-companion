"""Alembic 运行环境。

URL 解析优先级：
1. 环境变量 ``BACKEND_DATABASE_URL``（测试/CI 用）；
2. 否则用 ``backend.infrastructure.db.DB_PATH``（与运行时一致）。
"""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.infrastructure.db import DB_PATH

config = context.config

# 不调用 fileConfig(alembic.ini)：避免其重置 root 日志 handlers，冲掉后端 JSON 日志。
# alembic 自身日志交由后端 root logger 统一处理。

_url = os.getenv("BACKEND_DATABASE_URL") or f"sqlite:///{DB_PATH}"
config.set_main_option("sqlalchemy.url", _url)

# 我们用手写 SQL 迁移，不需要 autogenerate 的 metadata
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
