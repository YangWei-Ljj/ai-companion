"""Streamlit 前端 -> FastAPI 后端的 HTTP 客户端（httpx）。

前端不再直连 SQLite / LLM，一切经后端 API；SSE 流式聊天在此解析。
后端地址默认 http://localhost:8001，可用环境变量 BACKEND_URL 覆盖。
"""
from __future__ import annotations

import json
import os
import uuid
from typing import Callable, Iterator

import httpx

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001").rstrip("/")


class BackendError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        super().__init__(f"[{code}] {message}")


class BackendClient:
    def __init__(self, base_url: str = BACKEND_URL, timeout: float = 120.0):
        self.base_url = base_url
        self._client = httpx.Client(base_url=base_url, timeout=timeout)
        self.token: str | None = None

    # ---- 内部工具 ----
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @staticmethod
    def _check(resp: httpx.Response) -> dict:
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:  # noqa: BLE001
                body = {}
            raise BackendError(
                resp.status_code, body.get("code", "HTTP_ERROR"),
                body.get("message", resp.text[:200]))
        try:
            return resp.json()
        except Exception:  # noqa: BLE001
            return {}

    # ---- 健康 / 人格 ----
    def health(self) -> dict:
        return self._check(self._client.get("/api/health"))

    def llm_health(self) -> dict:
        return self._check(self._client.get("/api/health/llm", headers=self._headers()))

    def list_personas(self) -> list[dict]:
        return self._check(self._client.get("/api/personas", headers=self._headers()))

    # ---- 鉴权 ----
    def register(self, username: str, password: str, display_name: str | None = None) -> dict:
        return self._check(self._client.post(
            "/api/auth/register",
            json={"username": username, "password": password,
                  "display_name": display_name}))

    def login(self, username: str, password: str) -> dict:
        return self._check(self._client.post(
            "/api/auth/login", json={"username": username, "password": password}))

    def me(self) -> dict:
        return self._check(self._client.get("/api/auth/me", headers=self._headers()))

    # ---- 会话 ----
    def list_conversations(self) -> list[dict]:
        return self._check(self._client.get("/api/conversations", headers=self._headers()))

    def create_conversation(self, persona_id: str | None = None,
                            title: str | None = None) -> dict:
        body = {}
        if persona_id:
            body["persona_id"] = persona_id
        if title:
            body["title"] = title
        return self._check(self._client.post(
            "/api/conversations", json=body, headers=self._headers()))

    def delete_conversation(self, conv_id: str) -> dict:
        return self._check(self._client.delete(
            f"/api/conversations/{conv_id}", headers=self._headers()))

    def list_messages(self, conv_id: str) -> list[dict]:
        return self._check(self._client.get(
            f"/api/conversations/{conv_id}/messages", headers=self._headers()))

    def upload_file(self, conv_id: str, filename: str, content: bytes) -> dict:
        files = {"file": (filename, content, "text/plain")}
        return self._check(self._client.post(
            f"/api/conversations/{conv_id}/files",
            headers=self._headers(), files=files))

    # ---- SSE 流式聊天 ----
    def stream_message(self, conv_id: str, content: str) -> Iterator[dict]:
        """逐事件 yield 解析后的 dict：delta / done / error。"""
        with self._client.stream(
            "POST", f"/api/conversations/{conv_id}/messages/stream",
            json={"content": content}, headers=self._headers(),
        ) as resp:
            if resp.status_code >= 400:
                body = {}
                try:
                    body = resp.read()
                except Exception:  # noqa: BLE001
                    pass
                try:
                    info = json.loads(body)
                except Exception:  # noqa: BLE001
                    info = {"message": resp.text[:200]}
                raise BackendError(resp.status_code, info.get("code", "HTTP_ERROR"),
                                   info.get("message", "请求失败"))
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[len("data:"):].strip()
                if payload:
                    yield json.loads(payload)

    # ---- 后台导出任务 ----
    def create_export_job(self, conv_id: str) -> dict:
        idem = str(uuid.uuid4())
        return self._check(self._client.post(
            "/api/jobs/export",
            json={"conversation_id": conv_id},
            headers={**self._headers(), "Idempotency-Key": idem}))

    def get_job(self, job_id: str) -> dict:
        return self._check(self._client.get(
            f"/api/jobs/{job_id}", headers=self._headers()))
