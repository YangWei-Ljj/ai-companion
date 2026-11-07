"""初始化数据库并迁移旧 JSON 会话（幂等，可重复执行）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import init_db  # noqa: E402
from app import storage  # noqa: E402

if __name__ == "__main__":
    init_db()
    migrated = storage.migrate_all_legacy()
    print(f"数据库初始化完成：{Path(sys.path[0]).resolve() / 'data' / 'companion.db'}")
    print(f"旧 JSON 会话迁移数量：{migrated}")
