"""后台任务路由：导出会话 Markdown。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from backend.core.deps import rate_limited
from backend.core.logging import request_id_var
from backend.infrastructure import jobs as job_dispatch
from backend.infrastructure.audit import write_audit
from backend.schemas.job import ExportJobCreate
from backend.service import job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("/export")
def create_export_job(body: ExportJobCreate, request: Request,
                      response: Response,
                      user: dict = Depends(rate_limited)):
    idem = request.headers.get("Idempotency-Key")
    job = job_service.create_export_job(user["id"], body.conversation_id, idem)
    # 幂等重放：返回已有任务时标记 200
    if job["status"] in ("succeeded", "running") and idem:
        response.status_code = 200
    write_audit(request_id=request_id_var.get(), user_id=user["id"],
                action="job.export.create", resource_type="job",
                resource_id=job["id"])
    # 调度后台执行（fire-and-forget）
    job_dispatch.dispatch_export(job["id"])
    return {"job_id": job["id"], "status": job["status"]}


@router.get("/{job_id}")
def get_job(job_id: str, user: dict = Depends(rate_limited)):
    job = job_service.get_job_for_user(user["id"], job_id)
    import json as _json
    result = None
    if job.get("result_json"):
        try:
            result = _json.loads(job["result_json"]).get("markdown")
        except Exception:  # noqa: BLE001
            result = None
    return {
        "job_id": job["id"],
        "type": job["type"],
        "status": job["status"],
        "result": result,
        "error": job.get("error"),
        "created_at": job["created_at"],
        "finished_at": job.get("finished_at"),
    }
