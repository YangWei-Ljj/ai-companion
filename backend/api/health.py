"""健康检查路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.deps import rate_limited
from backend.infrastructure import llm

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health():
    return {"status": "ok", "provider": llm.provider(), "model": llm.model_name()}


@router.get("/health/llm")
def llm_health(user: dict = Depends(rate_limited)):
    ok, msg = llm.health()
    return {"ok": ok, "message": msg, "provider": llm.provider(),
            "model": llm.model_name()}
