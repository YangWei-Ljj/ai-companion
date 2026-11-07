"""鉴权路由：注册 / 登录 / 当前用户。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from backend.core.deps import get_current_user
from backend.core.logging import request_id_var, user_id_var
from backend.infrastructure.audit import write_audit
from backend.schemas.auth import LoginRequest, RegisterRequest, TokenOut, UserOut
from backend.service import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut)
def register(body: RegisterRequest, request: Request):
    result = auth_service.register(body.username, body.password, body.display_name)
    write_audit(request_id=request_id_var.get(), user_id=result["user"]["id"],
                action="auth.register", resource_type="user",
                resource_id=result["user"]["id"])
    return result


@router.post("/login", response_model=TokenOut)
def login(body: LoginRequest, request: Request):
    result = auth_service.login(body.username, body.password)
    write_audit(request_id=request_id_var.get(), user_id=result["user"]["id"],
                action="auth.login", resource_type="user",
                resource_id=result["user"]["id"])
    return result


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(get_current_user)):
    user_id_var.set(user["id"])
    return user
