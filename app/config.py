"""路径与运行配置。

- 所有路径均相对项目根解析，杜绝硬编码盘符；
- 支持 .env 文件（无 python-dotenv 时用内置最小加载器）。
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
UPLOAD_DIR = PROJECT_ROOT / "uploads"
PRESET_DIR = PROJECT_ROOT / "presets"
ASSET_DIR = PROJECT_ROOT / "创作资源"
DB_PATH = DATA_DIR / "companion.db"
# 原项目 JSON 会话目录（迁移脚本读取；兼容从旧目录启动）
LEGACY_SESSION_DIR = PROJECT_ROOT / "sessions"

for _d in (DATA_DIR, LOG_DIR, UPLOAD_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

# ===== 模型通道：默认 ollama（本地）；deepseek 为云端备选（.env 中 MODEL_PROVIDER=deepseek 一键切换） =====
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "ollama").strip().lower()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip()
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1").strip()
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b").strip()

LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
# 瞬时错误（连接失败/429/5xx）的 SDK 自动重试次数，指数退避由 openai SDK 实现
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))
LLM_MAX_HISTORY_MESSAGES = int(os.getenv("LLM_MAX_HISTORY_MESSAGES", "20"))

# 文件上传：仅文本，单文件 5MB
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
ALLOWED_UPLOAD_EXT = (".txt", ".md")
