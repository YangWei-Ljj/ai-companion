"""结构化 JSON 日志 + request-id / user_id 上下文。

- 每条日志一行 JSON，便于检索；
- request_id 由中间件生成并注入 contextvar，贯穿一次请求的所有日志；
- 严禁在日志中打印密钥（authorization / password / api_key）。
"""
from __future__ import annotations

import contextvars
import json
import logging
import time

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "user_id", default="-"
)

# 敏感字段名（子串匹配），日志中出现即打码
_SENSITIVE = ("authorization", "password", "api_key", "secret", "token")


def _scrub(extra: dict) -> dict:
    out = {}
    for k, v in extra.items():
        lk = k.lower()
        if any(s in lk for s in _SENSITIVE):
            out[k] = "***"
        else:
            out[k] = v
    return out


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
        }
        # 中间件附加的访问日志字段
        for k in ("method", "path", "status", "elapsed_ms"):
            v = getattr(record, k, None)
            if v is not None:
                payload[k] = v
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    import sys
    from app import config as app_config

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()
    formatter = JsonFormatter()

    # 控制台
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    # 文件：直接落盘，避免被 uvicorn / 进程重定向缓冲吞掉
    try:
        app_config.LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            app_config.LOG_DIR / "backend.json.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except Exception:  # noqa: BLE001
        pass

    # 静默 uvicorn 自带访问日志，避免与中间件日志重复
    logging.getLogger("uvicorn.access").handlers.clear()
