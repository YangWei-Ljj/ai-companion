"""后台任务相关模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ExportJobCreate(BaseModel):
    conversation_id: str = Field(..., max_length=64)


class JobOut(BaseModel):
    id: str
    type: str
    status: str
    result: str | None = None
    error: str | None = None
    created_at: str
    finished_at: str | None = None
