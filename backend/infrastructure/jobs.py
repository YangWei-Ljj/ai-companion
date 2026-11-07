"""后台任务调度：用进程内 asyncio 执行（无需 Redis/MQ）。

- 立即返回 job_id，导出在后台进行；
- 同步 DB 调用放到线程池，避免阻塞事件循环；
- 演进路线：多实例/横向扩展时换 Celery+Redis。
"""
from __future__ import annotations

import asyncio
import logging

from backend.service.job_service import run_export_job

logger = logging.getLogger("backend.jobs")


def dispatch_export(job_id: str) -> None:
    """在事件循环中调度导出任务（fire-and-forget）。"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 无运行中的事件循环（如脚本直调），直接同步执行
        run_export_job(job_id)
        return
    loop.create_task(_run_async(job_id))


async def _run_async(job_id: str) -> None:
    await asyncio.to_thread(run_export_job, job_id)
