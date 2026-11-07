"""后台导出任务：状态机 pending→running→succeeded/failed，幂等键防重。"""
from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy import text

from backend.core.exceptions import ForbiddenError, NotFoundError
from backend.core.security import utcnow_iso
from backend.infrastructure.db import get_engine
from backend.service import conversation_service, message_service

logger = logging.getLogger("backend.jobs")

JOB_TYPE_EXPORT = "export_conversation"


def create_export_job(user_id: str, conversation_id: str,
                      idempotency_key: str | None) -> dict:
    """幂等创建导出任务；同 user+type+idem_key 重复提交返回已有任务。"""
    # 先校验会话归属（不存在→404，他人→403）
    conversation_service.get_conversation_for_user(user_id, conversation_id)

    now = utcnow_iso()
    with get_engine().begin() as conn:
        if idempotency_key:
            existing = conn.execute(
                text(
                    "SELECT * FROM background_jobs WHERE user_id=:u AND type=:t "
                    "AND idempotency_key=:k"
                ),
                {"u": user_id, "t": JOB_TYPE_EXPORT, "k": idempotency_key},
            ).fetchone()
            if existing:
                return dict(existing._mapping)
        job_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO background_jobs(id,user_id,type,status,idempotency_key,"
                "payload_json,created_at) VALUES (:id,:u,:t,'pending',:k,:payload,:ts)"
            ),
            {"id": job_id, "u": user_id, "t": JOB_TYPE_EXPORT, "k": idempotency_key,
             "payload": json.dumps({"conversation_id": conversation_id},
                                   ensure_ascii=False),
             "ts": now},
        )
        row = conn.execute(
            text("SELECT * FROM background_jobs WHERE id=:i"), {"i": job_id}
        ).fetchone()
    return dict(row._mapping)


def get_job_for_user(user_id: str, job_id: str) -> dict:
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM background_jobs WHERE id=:i"), {"i": job_id}
        ).fetchone()
    if not row:
        raise NotFoundError("任务不存在")
    if row._mapping["user_id"] != user_id:
        raise ForbiddenError("无权访问该任务")
    return dict(row._mapping)


def _set_status(job_id: str, status: str, **fields) -> None:
    sets = ["status=:s"]
    params = {"s": status, "i": job_id}
    for k, v in fields.items():
        sets.append(f"{k}=:{k}")
        params[k] = v
    with get_engine().begin() as conn:
        conn.execute(
            text(f"UPDATE background_jobs SET {', '.join(sets)} WHERE id=:i"), params
        )


def run_export_job(job_id: str) -> None:
    """同步执行导出：读会话+消息→拼 Markdown→写 result_json。

    失败时把状态置 failed 并记录 error，绝不伪造成功。
    """
    try:
        _set_status(job_id, "running", started_at=utcnow_iso())
        with get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT * FROM background_jobs WHERE id=:i"), {"i": job_id}
            ).fetchone()
        if not row:
            return
        m = row._mapping
        payload = json.loads(m["payload_json"] or "{}")
        conv_id = payload["conversation_id"]
        conv = conversation_service.get_conversation_for_user(m["user_id"], conv_id)
        msgs = message_service.list_messages(conv_id)

        lines = [f"# 会话：{conv['title']}",
                 f"> 昵称：{conv['nick_name']} ｜ 性格：{conv['nature']}", ""]
        for m in msgs:
            if m["role"] == "file":
                continue
            speaker = "我" if m["role"] == "user" else conv["nick_name"]
            lines.append(f"**{speaker}**（{m['created_at']}）：\n\n{m['content']}\n")
        markdown = "\n".join(lines)

        _set_status(
            job_id, "succeeded",
            result_json=json.dumps({"markdown": markdown, "chars": len(markdown)},
                                   ensure_ascii=False),
            finished_at=utcnow_iso(),
        )
        logger.info("export job ok job_id=%s chars=%d", job_id, len(markdown))
    except Exception as exc:  # noqa: BLE001
        logger.exception("export job failed job_id=%s", job_id)
        _set_status(job_id, "failed", error=str(exc), finished_at=utcnow_iso())
