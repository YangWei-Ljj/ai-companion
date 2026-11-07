"""LLM 基础设施：复用第一轮 app.llm_client 的双通道能力（ollama 默认 / deepseek 备选）。

后端不在此重复造轮子，只做薄封装与异常类型别名，便于 service 层引用。
"""
from __future__ import annotations

from typing import Iterator

from app import config as app_config
from app import llm_client

# 异常别名，便于后端统一映射
LLMError = llm_client.LLMError


def model_name() -> str:
    return llm_client.model_name()


def provider() -> str:
    return app_config.MODEL_PROVIDER


def health() -> tuple[bool, str]:
    return llm_client.health_check()


def build_system_prompt(nick_name: str, nature: str) -> str:
    return llm_client.build_system_prompt(nick_name, nature)


def stream_chat(system_prompt: str, history: list[dict]) -> Iterator[str]:
    """逐段 yield 文本；失败抛 LLMError（中文友好消息）。"""
    yield from llm_client.stream_chat(system_prompt, history)
