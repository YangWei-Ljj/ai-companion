"""审计日志落库：记录 request_id / 操作者 / 动作 / 资源 / 结果 / 时间。"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import text

from backend.core.security import utcnow_iso
from backend.infrastructure.db import get_engine

logger = logging.getLogger("backend.audit")


def write_audit(
    *,
    request_id: str,
    user_id: str | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    result: str = "success",
    detail: dict[str, Any] | None = None,
) -> None:
    """写一条审计；写审计本身失败不应阻断主流程，故吞异常并记日志。"""
    import json

    try:
        with get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO audit_logs"
                    "(id, request_id, user_id, action, resource_type, resource_id,"
                    " result, detail_json, created_at) "
                    "VALUES (:id,:rid,:uid,:action,:rt,:resid,:result,:detail,:ts)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "rid": request_id,
                    "uid": user_id,
                    "action": action,
                    "rt": resource_type,
                    "resid": resource_id,
                    "result": result,
                    "detail": json.dumps(detail or {}, ensure_ascii=False),
                    "ts": utcnow_iso(),
                },
            )
    except Exception:  # noqa: BLE001
        logger.exception("audit write failed action=%s", action)
