"""统一双模型客户端：Ollama 本地（默认） / DeepSeek 云端备选，一套代码按配置切换。

设计要点：
- 工厂函数 ``_client()`` 按 ``MODEL_PROVIDER`` 构建 OpenAI 兼容客户端，双通道同源协议；
- 超时 + SDK 指数退避重试（``LLM_TIMEOUT_SECONDS`` / ``LLM_MAX_RETRIES``）；
- 所有对用户暴露的异常统一为 ``LLMError``（中文、不泄漏堆栈与密钥）；
- 结构化日志只记录 provider / 模型 / 耗时 / 错误类型，绝不记录 Key。

用法：
    from app.llm_client import health_check, stream_chat, model_name
"""
from __future__ import annotations

import logging
import time
import urllib.request
from typing import Iterator

import openai
from openai import OpenAI

from . import config

logger = logging.getLogger("companion.llm")


class LLMError(Exception):
    """对用户友好的模型调用异常：中文提示、不含堆栈与密钥。"""


def model_name() -> str:
    return config.OLLAMA_MODEL if config.MODEL_PROVIDER == "ollama" else config.DEEPSEEK_MODEL


def _base_url() -> str:
    return config.OLLAMA_BASE_URL if config.MODEL_PROVIDER == "ollama" else config.DEEPSEEK_BASE_URL


def _client() -> OpenAI:
    """客户端工厂：按 MODEL_PROVIDER 返回对应通道的 OpenAI 兼容客户端。

    - ollama 通道：api_key 占位（本地服务不校验）；
    - deepseek 通道：使用配置的真实 Key；
    - 显式传入 timeout 与 max_retries（瞬时错误自动指数退避重试）。
    """
    if config.MODEL_PROVIDER == "ollama":
        return OpenAI(
            api_key="ollama",
            base_url=config.OLLAMA_BASE_URL,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=config.LLM_MAX_RETRIES,
        )
    return OpenAI(
        api_key=config.DEEPSEEK_API_KEY or "missing-api-key",
        base_url=config.DEEPSEEK_BASE_URL,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
    )


def _friendly_message(exc: Exception) -> str:
    """把 openai SDK 异常翻译成可直接展示给用户的中文提示。"""
    if isinstance(exc, openai.APITimeoutError):
        return f"模型响应超时（>{config.LLM_TIMEOUT_SECONDS:.0f}s），请稍后重试"
    if isinstance(exc, openai.AuthenticationError):
        return "API Key 无效或未配置，请检查 .env 中的 DEEPSEEK_API_KEY"
    if isinstance(exc, openai.RateLimitError):
        return "触发限流，请稍后再试"
    if isinstance(exc, openai.APIStatusError):
        return f"模型服务返回错误 HTTP {exc.status_code}，请稍后重试"
    if isinstance(exc, openai.APIConnectionError):
        return "无法连接模型服务，请检查 Ollama 是否启动 / 网络是否通畅"
    return f"模型调用失败：{exc}"


def health_check() -> tuple[bool, str]:
    """启动自检：Key 缺失 / Ollama 未运行给出可操作的中文提示。"""
    if config.MODEL_PROVIDER == "ollama":
        # /v1 之外的原生探测端点
        probe = config.OLLAMA_BASE_URL.replace("/v1", "").rstrip("/") + "/api/tags"
        try:
            with urllib.request.urlopen(probe, timeout=3) as resp:
                if resp.status == 200:
                    return True, f"本地 Ollama 已连接（{config.OLLAMA_MODEL}）"
            return False, "Ollama 服务无响应，请先启动 Ollama（命令行执行 ollama serve）"
        except Exception as exc:  # noqa: BLE001
            logger.info("ollama health check failed: %s", exc)
            return False, f"无法连接 Ollama（{config.OLLAMA_BASE_URL}）：{exc}。请启动 Ollama 后重试"
    if not config.DEEPSEEK_API_KEY or config.DEEPSEEK_API_KEY == "missing-api-key":
        return False, "未配置 DEEPSEEK_API_KEY：请复制 .env.example 为 .env 并填入 Key，或切换 MODEL_PROVIDER=ollama"
    # 轻量验证模型列表（失败通常是 Key 错误）
    try:
        client = _client()
        client.models.list()
        return True, f"云端 DeepSeek 已连接（{config.DEEPSEEK_MODEL}）"
    except Exception as exc:  # noqa: BLE001
        logger.info("deepseek health check failed: %s", type(exc).__name__)
        return False, f"DeepSeek 连接失败：{exc}。请检查 Key 与网络"


def build_system_prompt(nick_name: str, nature: str) -> str:
    return (
        f"你叫 {nick_name}，性别为女性，现在是用户的真实伴侣，请完全代入伴侣角色。\n"
        "规则：\n"
        "1. 每次只回1条消息\n"
        "2. 禁止任何场景或状态描述性文字\n"
        "3. 匹配用户的语言\n"
        "4. 回复简短，像微信聊天一样\n"
        "5. 可以用❤️🌸等 emoji 表情\n"
        "6. 用符合伴侣性格的方式对话\n"
        "7. 回复内容要充分体现伴侣的性格特征\n"
        f"伴侣性格：\n- {nature}\n"
        "你必须严格遵守上述规则来回复。"
    )


def trim_history(messages: list[dict]) -> list[dict]:
    """上下文裁剪：只保留最近 N 条消息，防止超出窗口。"""
    max_n = config.LLM_MAX_HISTORY_MESSAGES
    if len(messages) <= max_n:
        return messages
    return messages[-max_n:]


def stream_chat(system_prompt: str, messages: list[dict]) -> Iterator[str]:
    """流式对话，逐段 yield 文本。

    - 网络/鉴权/超时等异常统一包装为 LLMError（中文友好消息）后抛出，由 UI 层提示；
    - 结构化日志记录耗时与错误类型（不含 Key）；
    - 调用前已由 SDK 按 max_retries 自动退避重试瞬时错误。
    """
    payload = [{"role": "system", "content": system_prompt}] + trim_history(messages)
    t0 = time.perf_counter()
    n_deltas = 0
    try:
        stream = _client().chat.completions.create(
            model=model_name(),
            messages=payload,
            stream=True,
            temperature=config.LLM_TEMPERATURE,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                n_deltas += 1
                yield delta
    except LLMError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "llm call failed provider=%s model=%s error=%s elapsed=%.2fs",
            config.MODEL_PROVIDER, model_name(), type(exc).__name__, time.perf_counter() - t0,
        )
        raise LLMError(_friendly_message(exc)) from exc
    logger.info(
        "llm call ok provider=%s model=%s deltas=%d elapsed=%.2fs",
        config.MODEL_PROVIDER, model_name(), n_deltas, time.perf_counter() - t0,
    )
