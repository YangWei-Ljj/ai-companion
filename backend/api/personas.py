"""人格预设路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.core.deps import rate_limited
from backend.service import persona_service

router = APIRouter(prefix="/api/personas", tags=["personas"])


@router.get("")
def list_personas(user: dict = Depends(rate_limited)):
    return persona_service.list_personas()
