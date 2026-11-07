"""FastAPI 依赖注入：当前用户 / 进程内限流。"""
from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, Header

from backend.core.config import settings
from backend.core.exceptions import AuthRequiredError, RateLimitedError
from backend.core.logging import user_id_var
from backend.service import auth_service

# 进程内滑动窗口限流：{user_id: deque[timestamps]}（单实例足够，多实例换 Redis）
_buckets: dict[str, deque] = defaultdict(deque)


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization:
        raise AuthRequiredError("缺少 Authorization 头")
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthRequiredError("Authorization 格式应为 Bearer <token>")
    user = auth_service.get_user_by_token(parts[1].strip())
    user_id_var.set(user["id"])
    return user


def rate_limited(user: dict = Depends(get_current_user)) -> dict:
    """已认证用户按每分钟窗口限流；超限 429。"""
    now = time.time()
    dq = _buckets[user["id"]]
    while dq and now - dq[0] > 60:
        dq.popleft()
    if len(dq) >= settings.RATE_LIMIT_PER_MINUTE:
        raise RateLimitedError()
    dq.append(now)
    return user


def reset_rate_limiter() -> None:
    """测试用：清空限流桶。"""
    _buckets.clear()
