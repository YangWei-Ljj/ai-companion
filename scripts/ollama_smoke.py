"""本地 Ollama 真实冒烟：用当前配置的模型（默认 qwen3.5:9b）做一次真实流式对话。

用途：CI 离线测试之外，人工验证 ollama 通道端到端可用。
用法：
    python scripts/ollama_smoke.py
退出码：0=成功；1=自检失败。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, llm_client  # noqa: E402


def main() -> None:
    ok, msg = llm_client.health_check()
    print(f"[health] ok={ok} msg={msg}")
    if not ok:
        sys.exit(1)

    print(f"[provider] MODEL_PROVIDER={config.MODEL_PROVIDER} model={llm_client.model_name()} "
          f"base_url={config.OLLAMA_BASE_URL}")
    print("[reply] <<<")
    chunks = 0
    for delta in llm_client.stream_chat(
        "你是一个简洁的中文助手。",
        [{"role": "user", "content": "请用不超过30个中文字介绍一下你自己。"}],
    ):
        print(delta, end="", flush=True)
        chunks += 1
    print(f"\n[done] chunks={chunks}")


if __name__ == "__main__":
    main()
