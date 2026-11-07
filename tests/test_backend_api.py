"""后端 API 集成测试（fastapi TestClient，离线 Mock LLM）。

每个用例使用独立临时 SQLite 库，启动时自动跑 Alembic 迁移 + 种子人格。
覆盖：鉴权、越权隔离、输入校验、SSE 流式、限流、幂等、后台任务状态机、审计。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    db_file = tmp_path / "test_backend.db"
    monkeypatch.setenv("BACKEND_DATABASE_URL", f"sqlite:///{db_file}")
    import backend.infrastructure.db as dbmod
    monkeypatch.setattr(dbmod, "DB_PATH", str(db_file))
    dbmod.reset_engine()

    from backend.core.deps import reset_rate_limiter
    reset_rate_limiter()

    from backend.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


from fastapi.testclient import TestClient  # noqa: E402


def _register(client, username="alice", password="secret123"):
    r = client.post("/api/auth/register",
                    json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- 鉴权 ----------

def test_register_login_me(client):
    data = _register(client, "alice")
    token = data["token"]
    assert data["user"]["username"] == "alice"

    r = client.get("/api/auth/me", headers=_auth(token))
    assert r.status_code == 200 and r.json()["username"] == "alice"

    # 登录
    r = client.post("/api/auth/login", json={"username": "alice", "password": "secret123"})
    assert r.status_code == 200 and r.json()["token"]


def test_duplicate_username_conflict(client):
    _register(client, "bob")
    r = client.post("/api/auth/register",
                    json={"username": "bob", "password": "secret123"})
    assert r.status_code == 409 and r.json()["code"] == "CONFLICT"


def test_login_wrong_password(client):
    _register(client, "carol")
    r = client.post("/api/auth/login",
                     json={"username": "carol", "password": "wrong-pass"})
    assert r.status_code == 401 and r.json()["code"] == "AUTH_INVALID"


def test_no_token_and_bad_token(client):
    r = client.get("/api/conversations")
    assert r.status_code == 401 and r.json()["code"] == "AUTH_REQUIRED"
    r = client.get("/api/conversations", headers=_auth("not-a-real-token"))
    assert r.status_code == 401 and r.json()["code"] == "TOKEN_INVALID"


def test_validation_register_short_password(client):
    r = client.post("/api/auth/register",
                    json={"username": "dave", "password": "123"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_ERROR"


# ---------- 会话与越权隔离 ----------

def test_conversation_crud_and_isolation(client):
    a = _register(client, "alice2")["token"]
    b = _register(client, "bob2")["token"]

    # alice 建会话
    r = client.post("/api/conversations",
                    headers=_auth(a),
                    json={"persona_id": "gentle", "title": "alice的会话"})
    assert r.status_code == 200, r.text
    conv_id = r.json()["id"]
    assert r.json()["nick_name"] == "小柔"

    # alice 能列到
    convs = client.get("/api/conversations", headers=_auth(a)).json()
    assert len(convs) == 1

    # bob 访问 alice 的会话 -> 403
    r = client.get(f"/api/conversations/{conv_id}", headers=_auth(b))
    assert r.status_code == 403 and r.json()["code"] == "FORBIDDEN"

    # bob 列不到 alice 的会话
    assert client.get("/api/conversations", headers=_auth(b)).json() == []

    # 不存在的会话 -> 404
    r = client.get("/api/conversations/nope", headers=_auth(a))
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND"


def test_audit_logged_on_forbidden(client):
    a = _register(client, "alice3")["token"]
    b = _register(client, "bob3")["token"]
    r = client.post("/api/conversations", headers=_auth(a), json={})
    conv_id = r.json()["id"]
    # bob 越权访问
    client.get(f"/api/conversations/{conv_id}", headers=_auth(b))

    import backend.infrastructure.db as dbmod
    from sqlalchemy import text
    with dbmod.get_engine().connect() as conn:
        rows = conn.execute(
            text("SELECT result, action FROM audit_logs WHERE result='denied'")
        ).fetchall()
    assert any(row._mapping["action"] == "conversation.access" for row in rows)


# ---------- SSE 流式（Mock LLM） ----------

def _mock_llm(monkeypatch, deltas=("你", "好", "呀"), error=None):
    import backend.infrastructure.llm as llm_mod

    def fake_stream(system_prompt, history):
        if error:
            raise error
        for d in deltas:
            yield d

    monkeypatch.setattr(llm_mod, "stream_chat", fake_stream)


def test_sse_stream_and_persist(client, monkeypatch):
    _mock_llm(monkeypatch)
    a = _register(client, "alice4")["token"]
    conv_id = client.post("/api/conversations", headers=_auth(a),
                          json={}).json()["id"]

    r = client.post(f"/api/conversations/{conv_id}/messages/stream",
                    headers=_auth(a), json={"content": "在吗"})
    assert r.status_code == 200
    body = r.text
    assert "你好呀" in body  # 增量拼接
    assert '"type":"done"' in body

    # 落库：user + assistant
    msgs = client.get(f"/api/conversations/{conv_id}/messages",
                      headers=_auth(a)).json()
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles
    assert any(m["content"] == "你好呀" for m in msgs)


def test_sse_empty_message_rejected(client, monkeypatch):
    _mock_llm(monkeypatch)
    a = _register(client, "alice5")["token"]
    conv_id = client.post("/api/conversations", headers=_auth(a),
                          json={}).json()["id"]
    r = client.post(f"/api/conversations/{conv_id}/messages/stream",
                    headers=_auth(a), json={"content": "   "})
    assert r.status_code == 422


def test_sse_too_long_rejected(client):
    a = _register(client, "alice6")["token"]
    conv_id = client.post("/api/conversations", headers=_auth(a),
                          json={}).json()["id"]
    r = client.post(f"/api/conversations/{conv_id}/messages/stream",
                    headers=_auth(a), json={"content": "x" * 5000})
    assert r.status_code == 422


def test_sse_llm_error_event(client, monkeypatch):
    from backend.infrastructure.llm import LLMError
    _mock_llm(monkeypatch, error=LLMError("模型超时"))
    a = _register(client, "alice7")["token"]
    conv_id = client.post("/api/conversations", headers=_auth(a),
                          json={}).json()["id"]
    r = client.post(f"/api/conversations/{conv_id}/messages/stream",
                    headers=_auth(a), json={"content": "hi"})
    assert r.status_code == 200
    assert '"type":"error"' in r.text
    # 失败也要落库 assistant 消息（标注失败），不伪造成功
    msgs = client.get(f"/api/conversations/{conv_id}/messages",
                      headers=_auth(a)).json()
    assert any(m["role"] == "assistant" and "失败" in m["content"] for m in msgs)


# ---------- 限流 ----------

def test_rate_limit_429(client, monkeypatch):
    from backend.core.config import settings
    monkeypatch.setattr(settings, "RATE_LIMIT_PER_MINUTE", 5)
    from backend.core.deps import reset_rate_limiter
    reset_rate_limiter()
    a = _register(client, "alice8")["token"]
    codes = []
    for _ in range(8):
        codes.append(client.get("/api/conversations", headers=_auth(a)).status_code)
    assert 429 in codes
    assert codes.count(429) >= 1


# ---------- 后台导出任务 + 幂等 ----------

def test_export_job_state_machine_and_idempotency(client, monkeypatch):
    a = _register(client, "alice9")["token"]
    conv_id = client.post("/api/conversations", headers=_auth(a),
                          json={}).json()["id"]
    # 直接写两条消息到库
    from backend.service import message_service
    message_service.add_message(conv_id, "user", "你好")
    message_service.add_message(conv_id, "assistant", "你好呀")

    headers = {**_auth(a), "Idempotency-Key": "export-123"}
    r1 = client.post("/api/jobs/export", headers=headers,
                     json={"conversation_id": conv_id})
    assert r1.status_code in (200, 201)
    job_id = r1.json()["job_id"]

    # 同步跑一次任务（绕过事件循环等待）
    from backend.service.job_service import run_export_job
    run_export_job(job_id)

    r = client.get(f"/api/jobs/{job_id}", headers=_auth(a))
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"
    assert "你好呀" in r.json()["result"]

    # 幂等重放：相同 key 返回同一 job
    r2 = client.post("/api/jobs/export", headers=headers,
                     json={"conversation_id": conv_id})
    assert r2.json()["job_id"] == job_id


def test_export_job_other_user_forbidden(client):
    a = _register(client, "aliceA")["token"]
    b = _register(client, "bobA")["token"]
    conv_id = client.post("/api/conversations", headers=_auth(a),
                           json={}).json()["id"]
    r = client.post("/api/jobs/export", headers=_auth(b),
                     json={"conversation_id": conv_id})
    assert r.status_code == 403


def test_health_and_personas(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    a = _register(client, "aliceB")["token"]
    r = client.get("/api/personas", headers=_auth(a))
    assert r.status_code == 200 and len(r.json()) >= 3
