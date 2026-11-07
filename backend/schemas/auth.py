"""鉴权相关请求/响应。"""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.core.config import settings


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=settings.USERNAME_MIN,
                          max_length=settings.USERNAME_MAX, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(..., min_length=settings.MIN_PASSWORD_LEN, max_length=128)
    display_name: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=settings.USERNAME_MAX)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str | None = None


class TokenOut(BaseModel):
    token: str
    user: UserOut
