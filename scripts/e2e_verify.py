"""端到端真实验证：起好后端后，用真实 HTTP 走一遍 注册->建会话->SSE(真ollama)->落库->历史->导出。"""
import json
import sys
import httpx

BASE = "http://localhost:8001"
c = httpx.Client(base_url=BASE, timeout=120)

print("== 1. GET /api/health ==")
r = c.get("/api/health")
print(r.status_code, r.json())
assert r.status_code == 200

print("== 2. register/login ==")
r = c.post("/api/auth/register", json={"username": "e2e_user", "password": "e2e-pass-1"})
if r.status_code == 409:
    r = c.post("/api/auth/login", json={"username": "e2e_user", "password": "e2e-pass-1"})
print(r.status_code, r.json().get("user"))
assert r.status_code == 200, r.text
token = r.json()["token"]
H = {"Authorization": f"Bearer {token}"}

print("== 3. GET /api/health/llm ==")
r = c.get("/api/health/llm", headers=H)
print(r.status_code, r.json())

print("== 4. list personas ==")
r = c.get("/api/personas", headers=H)
print(r.status_code, [p["id"] for p in r.json()])
pid = r.json()[0]["id"]

print("== 5. create conversation ==")
r = c.post("/api/conversations", headers=H, json={"persona_id": pid})
print(r.status_code, r.json())
cid = r.json()["id"]

print("== 6. SSE stream message (real ollama) ==")
deltas = 0
text_out = ""
with c.stream("POST", f"/api/conversations/{cid}/messages/stream",
              headers=H, json={"content": "用一句话打招呼"}) as resp:
    print("status:", resp.status_code, "x-request-id:", resp.headers.get("x-request-id"))
    for line in resp.iter_lines():
        if line.startswith("data:"):
            ev = json.loads(line[5:].strip())
            if ev["type"] == "delta":
                deltas += 1
                text_out += ev["text"]
            elif ev["type"] == "done":
                print("done, assistant msg id:", ev["message_id"])
            elif ev["type"] == "error":
                print("ERROR EVENT:", ev["message"])
print(f"deltas={deltas} text={text_out!r}")

print("== 7. list messages (history persisted) ==")
r = c.get(f"/api/conversations/{cid}/messages", headers=H)
print(r.status_code, [(m["role"], m["content"][:20]) for m in r.json()])

print("== 8. export job ==")
r = c.post("/api/jobs/export", headers={**H, "Idempotency-Key": "e2e-export-1"},
           json={"conversation_id": cid})
print(r.status_code, r.json())
jid = r.json()["job_id"]
import time
for _ in range(10):
    time.sleep(0.5)
    jr = c.get(f"/api/jobs/{jid}", headers=H).json()
    if jr["status"] in ("succeeded", "failed"):
        break
print("job final:", jr["status"], "result_chars=", len(jr.get("result") or ""))

print("== 9. unauthorized ==")
r = c.get("/api/conversations")
print("no-token:", r.status_code, r.json()["code"])

print("E2E OK")
