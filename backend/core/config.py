"""后端配置（pydantic-settings）。

设计约定：
- 先 ``from app import config as app_config`` 触发第一轮 .env 加载，
  LLM 相关配置继续复用 app.config（默认本地 Ollama，DeepSeek 仅备选）；
- 本文件只承载「后端新增」的配置项（端口、DB、鉴权、限流、校验阈值）；
- 所有敏感值只走环境变量，绝不硬编码密钥。
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from app import config as app_config  # noqa: F401  触发 .env 加载


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ---- HTTP 服务 ----
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001

    # ---- 数据库 ----
    # 后端使用独立库 data/backend.db，与第一轮 demo 库(data/companion.db)隔离，
    # 避免 enterprise 版 messages/conversations 与旧 sessions/messages 表名冲突。
    DB_PATH: str = str(app_config.DATA_DIR / "backend.db")

    # ---- 本地演示鉴权（非生产级，仅本地演示）----
    PBKDF2_ITERATIONS: int = 200_000
    TOKEN_TTL_HOURS: int = 72

    # ---- 限流：每用户每分钟窗口 ----
    RATE_LIMIT_PER_MINUTE: int = 60

    # ---- 输入校验 ----
    USERNAME_MIN: int = 3
    USERNAME_MAX: int = 32
    MIN_PASSWORD_LEN: int = 6
    MAX_MESSAGE_LEN: int = 4000
    MAX_UPLOAD_BYTES: int = app_config.MAX_UPLOAD_BYTES
    ALLOWED_UPLOAD_EXT: tuple = (".txt", ".md")


settings = Settings()
