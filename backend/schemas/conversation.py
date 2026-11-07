"""会话与消息相关模型。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.core.config import settings


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    persona_id: str | None = Field(default=None, max_length=64)
    nick_name: str | None = Field(default=None, max_length=64)
    nature: str | None = Field(default=None, max_length=2000)


class ConversationUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    persona_id: str | None = Field(default=None, max_length=64)
    nick_name: str | None = Field(default=None, max_length=64)
    nature: str | None = Field(default=None, max_length=2000)


class ConversationOut(BaseModel):
    id: str
    title: str
    persona_id: str | None
    nick_name: str
    nature: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: str


class MessageStreamRequest(BaseModel):
    content: str = Field(..., max_length=settings.MAX_MESSAGE_LEN)
