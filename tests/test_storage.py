"""会话/消息 CRUD 与历史裁剪的最小冒烟测试（不访问网络）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def temp_db(monkeypatch, tmp_path):
    import app.config as config
    from app.db import init_db

    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test_companion.db")
    init_db()
    yield tmp_path


def test_session_crud(temp_db):
    from app import storage

    sid = storage.create_session("小柔", "温柔", persona_id="gentle", title="测试")
    assert storage.get_session(sid)["nick_name"] == "小柔"

    storage.add_message(sid, "user", "你好")
    storage.add_message(sid, "assistant", "你好呀")
    msgs = storage.list_messages(sid)
    assert len(msgs) == 2 and msgs[0]["role"] == "user"
    assert msgs[0]["created_at"]  # 时间戳已记录

    storage.rename_session(sid, "重命名")
    assert storage.get_session(sid)["title"] == "重命名"

    md = storage.export_markdown(sid)
    assert "重命名" in md and "你好呀" in md

    storage.delete_session(sid)
    assert storage.get_session(sid) is None
    assert storage.list_messages(sid) == []


def test_trim_history(temp_db):
    from app import llm_client

    msgs = [{"role": "user", "content": str(i)} for i in range(50)]
    trimmed = llm_client.trim_history(msgs)
    assert len(trimmed) == 20
    assert trimmed[-1]["content"] == "49"


class _FakeUpload:
    def __init__(self, name: str, raw: bytes):
        self.name = name
        self._raw = raw

    def getvalue(self) -> bytes:
        return self._raw


def test_file_ingest_ok_and_reject():
    from app import file_ingest

    ok = file_ingest.read_text_file(_FakeUpload("a.txt", "你好".encode("utf-8")))
    assert ok == "你好"
    gbk = file_ingest.read_text_file(_FakeUpload("b.md", "GBK内容".encode("gbk")))
    assert "内容" in gbk

    with pytest.raises(file_ingest.UploadError):
        file_ingest.read_text_file(_FakeUpload("a.exe", b"x"))

    big = _FakeUpload("big.txt", b"a" * (5 * 1024 * 1024 + 1))
    with pytest.raises(file_ingest.UploadError):
        file_ingest.read_text_file(big)
