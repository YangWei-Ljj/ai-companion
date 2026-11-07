"""FastAPI 应用入口（模块化单体后端）。

启动：
    python -m uvicorn backend.main:app --port 8001
启动时自动执行 Alembic 迁移（upgrade head）并种子人格预设。
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.exceptions import AppError
from backend.core.logging import setup_logging, request_id_var, user_id_var
from backend.core.deps import reset_rate_limiter

PROJECT_ROOT = Path(__file__).resolve().parent.parent

setup_logging()
logger = logging.getLogger("backend")


def run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parent
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(PROJECT_ROOT))
    command.upgrade(cfg, "head")


def create_app() -> FastAPI:
    app = FastAPI(title="AI 智能伴侣后端", version="2.0.0")

    # ---------- 中间件：request-id 贯穿 + 访问日志 ----------
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        req_id = uuid.uuid4().hex
        request_id_var.set(req_id)
        user_id_var.set("-")
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = int((time.perf_counter() - start) * 1000)
            logger.exception(
                "unhandled error", extra={"method": request.method,
                                          "path": request.url.path,
                                          "status": 500, "elapsed_ms": elapsed})
            raise
        elapsed = int((time.perf_counter() - start) * 1000)
        response.headers["X-Request-ID"] = req_id
        logger.info(
            "access", extra={"method": request.method, "path": request.url.path,
                             "status": response.status_code, "elapsed_ms": elapsed})
        return response

    # ---------- 统一异常处理 ----------
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        rid = request_id_var.get()
        return JSONResponse(
            status_code=exc.http_status,
            content={"code": exc.code, "message": exc.message,
                     "request_id": rid, "trace_id": rid},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        rid = request_id_var.get()
        # 提取第一条错误信息，避免把超长校验细节直接抛给用户
        errors = exc.errors()
        msg = "请求参数不合法"
        if errors:
            first = errors[0]
            loc = ".".join(str(x) for x in first.get("loc", []) if x != "body")
            msg = f"参数 {loc} 不合法: {first.get('msg', '')}" if loc else first.get("msg", msg)
        return JSONResponse(
            status_code=422,
            content={"code": "VALIDATION_ERROR", "message": msg,
                     "request_id": rid, "trace_id": rid},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception):
        rid = request_id_var.get()
        logger.exception("unhandled 500", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={"code": "INTERNAL_ERROR", "message": "服务器内部错误",
                     "request_id": rid, "trace_id": rid},
        )

    # ---------- 路由 ----------
    from backend.api import auth, conversations, health, jobs, personas
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(personas.router)
    app.include_router(conversations.router)
    app.include_router(jobs.router)

    @app.on_event("startup")
    def _startup():
        run_migrations()  # 迁移期间 alembic 会重配 logging，故在其后再挂我们的 handler
        setup_logging()
        from backend.service import persona_service
        n = persona_service.seed_personas()
        logger.info("backend startup ok, personas seeded=%d", n)

    return app


app = create_app()
