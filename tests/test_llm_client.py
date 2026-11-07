"""llm_client 双通道切换 / 健康检查 / 流式 / 异常映射的离线单测。

全部 Mock 模型与网络，快速、确定性、常驻测试集。
真实 ollama 冒烟见 scripts/ollama_smoke.py（手动跑）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import app.config as config  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_provider(monkeypatch):
    """每个用例后复原 MODEL_PROVIDER，避免串扰。"""
    original = config.MODEL_PROVIDER
    yield
    monkeypatch.setattr(config, "MODEL_PROVIDER", original)


# ---------- 双通道工厂 ----------

def test_default_provider_is_ollama():
    """强制约束：配置加载默认值必须是 ollama。"""
    src = Path(config.__file__).read_text(encoding="utf-8")
    assert 'MODEL_PROVIDER", "ollama"' in src, "config.py 默认通道必须为 ollama"


def test_factory_switch_ollama(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(config, "MODEL_PROVIDER", "ollama")
    assert llm_client.model_name() == config.OLLAMA_MODEL
    assert "11434" in llm_client._base_url()
    client = llm_client._client()
    assert client.api_key == "ollama"
    assert str(client.base_url).rstrip("/") == config.OLLAMA_BASE_URL.rstrip("/")
    assert client.max_retries == config.LLM_MAX_RETRIES


def test_factory_switch_deepseek(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(config, "MODEL_PROVIDER", "deepseek")
    assert llm_client.model_name() == config.DEEPSEEK_MODEL
    assert "deepseek.com" in llm_client._base_url()
    # 未配置 Key 时用占位 key 构造（不触网），保证工厂不抛异常
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    client = llm_client._client()
    assert client.api_key == "missing-api-key"


# ---------- 健康检查 ----------

def test_health_check_ollama_down(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(config, "MODEL_PROVIDER", "ollama")

    def boom(*args, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", boom)
    ok, msg = llm_client.health_check()
    assert ok is False and "Ollama" in msg


def test_health_check_ollama_up(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(config, "MODEL_PROVIDER", "ollama")

    class _FakeResp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(llm_client.urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    ok, msg = llm_client.health_check()
    assert ok is True and config.OLLAMA_MODEL in msg


def test_health_check_deepseek_no_key(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(config, "MODEL_PROVIDER", "deepseek")
    monkeypatch.setattr(config, "DEEPSEEK_API_KEY", "")
    ok, msg = llm_client.health_check()
    assert ok is False and "DEEPSEEK_API_KEY" in msg


# ---------- system prompt / 历史裁剪 ----------

def test_build_system_prompt_contains_persona():
    from app import llm_client

    p = llm_client.build_system_prompt("小柔", "温柔体贴")
    assert "小柔" in p and "温柔体贴" in p


def test_trim_history_boundary(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(config, "LLM_MAX_HISTORY_MESSAGES", 5)
    short = [{"role": "user", "content": "x"}]
    assert llm_client.trim_history(short) == short  # 不足阈值原样返回

    long = [{"role": "user", "content": str(i)} for i in range(10)]
    trimmed = llm_client.trim_history(long)
    assert len(trimmed) == 5
    assert trimmed[-1]["content"] == "9"  # 保留尾部最新对话


# ---------- 流式（Mock chunk） ----------

class _Delta:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.delta = _Delta(content)


class _Chunk:
    def __init__(self, content):
        # content=None 表示空 choices 分支
        self.choices = [_Choice(content)] if content is not None else []


class _FakeCompletions:
    def __init__(self):
        self.last_kwargs: dict = {}

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return iter([_Chunk("你"), _Chunk(None), _Chunk("好"), _Chunk("呀")])


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


def test_stream_chat_mock(monkeypatch):
    from app import llm_client

    fake = _FakeClient()
    monkeypatch.setattr(llm_client, "_client", lambda: fake)
    out = "".join(llm_client.stream_chat("系统提示", [{"role": "user", "content": "hi"}]))
    assert out == "你好呀"

    kw = fake.chat.completions.last_kwargs
    assert kw["messages"][0] == {"role": "system", "content": "系统提示"}
    assert kw["stream"] is True
    assert kw["model"] == llm_client.model_name()


def test_stream_chat_trimmed_payload(monkeypatch):
    from app import llm_client

    monkeypatch.setattr(config, "LLM_MAX_HISTORY_MESSAGES", 2)
    fake = _FakeClient()
    monkeypatch.setattr(llm_client, "_client", lambda: fake)
    history = [{"role": "user", "content": str(i)} for i in range(5)]
    "".join(llm_client.stream_chat("sys", history))
    sent = fake.chat.completions.last_kwargs["messages"]
    # system + 最近 2 条
    assert len(sent) == 3
    assert sent[-1]["content"] == "4"


# ---------- 异常映射 ----------

def _req():
    import httpx

    return httpx.Request("POST", "http://localhost/v1/chat/completions")


def test_stream_chat_timeout_mapped(monkeypatch):
    import openai

    from app import llm_client

    def boom():
        raise openai.APITimeoutError(request=_req())

    monkeypatch.setattr(llm_client, "_client", boom)
    with pytest.raises(llm_client.LLMError, match="超时"):
        "".join(llm_client.stream_chat("sys", []))


def test_stream_chat_conn_error_mapped(monkeypatch):
    import openai

    from app import llm_client

    def boom():
        raise openai.APIConnectionError(request=_req())

    monkeypatch.setattr(llm_client, "_client", boom)
    with pytest.raises(llm_client.LLMError, match="连接"):
        "".join(llm_client.stream_chat("sys", []))


def test_stream_chat_auth_error_mapped(monkeypatch):
    import httpx
    import openai

    from app import llm_client

    def boom():
        req = _req()
        raise openai.AuthenticationError(
            message="invalid api key",
            response=httpx.Response(401, request=req),
            body=None,
        )

    monkeypatch.setattr(llm_client, "_client", boom)
    with pytest.raises(llm_client.LLMError, match="Key"):
        "".join(llm_client.stream_chat("sys", []))


# ---------- 上传边界补充 ----------

class _FakeUpload:
    def __init__(self, name: str, raw: bytes):
        self.name = name
        self._raw = raw

    def getvalue(self) -> bytes:
        return self._raw


def test_file_ingest_undecodable_bytes():
    from app import file_ingest

    with pytest.raises(file_ingest.UploadError):
        file_ingest.read_text_file(_FakeUpload("bad.txt", b"\xff\xfe\x00\x01\x02"))
