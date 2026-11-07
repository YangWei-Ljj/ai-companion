"""AI 智能伴侣 · 第二轮：Streamlit 前端（真实 HTTP 调用 FastAPI 后端）。

前端只通过 app.backend_client 与 :8001 后端通信，不直连 SQLite / LLM。
启动：streamlit run app/main.py --server.port 8511
（需先启动后端：uvicorn backend.main:app --port 8001）
"""
from __future__ import annotations

import time

import streamlit as st

from app.backend_client import BackendClient, BackendError, BACKEND_URL

st.set_page_config(page_title="AI智能伴侣", page_icon="🤖", layout="wide",
                   initial_sidebar_state="expanded")


# ---------------- 客户端初始化 ----------------
@st.cache_resource(show_spinner=False)
def get_client() -> BackendClient:
    return BackendClient()


client = get_client()


def require_backend_up() -> bool:
    try:
        client.health()
        return True
    except Exception:  # noqa: BLE001
        return False


# ---------------- 登录 / 注册 ----------------
if not client.token:
    st.title("🤖 AI 智能伴侣 · 登录")
    if not require_backend_up():
        st.error(f"后端不可达（{BACKEND_URL}）。请先启动：uvicorn backend.main:app --port 8001")
        st.stop()

    tab_login, tab_reg = st.tabs(["登录", "注册"])
    with tab_login:
        u = st.text_input("用户名", key="login_u")
        p = st.text_input("密码", type="password", key="login_p")
        if st.button("登录", type="primary"):
            try:
                data = client.login(u, p)
                client.token = data["token"]
                st.session_state.user = data["user"]
                st.rerun()
            except BackendError as e:
                st.error(f"{e}")
    with tab_reg:
        u2 = st.text_input("用户名（3-32位字母数字）", key="reg_u")
        p2 = st.text_input("密码（至少6位）", type="password", key="reg_p")
        if st.button("注册并登录"):
            try:
                data = client.register(u2, p2)
                client.token = data["token"]
                st.session_state.user = data["user"]
                st.success("注册成功"); st.rerun()
            except BackendError as e:
                st.error(f"{e}")
    st.stop()


# ---------------- 已登录：侧边栏 ----------------
with st.sidebar:
    st.caption(f"已登录：{st.session_state.get('user', {}).get('username', '')}")
    st.subheader("模型状态")
    try:
        h = client.llm_health()
        st.markdown(f"**Provider**：`{h.get('provider')}`\n\n**Model**：`{h.get('model')}`\n\n"
                    f"{'✅' if h.get('ok') else '⚠️'} {h.get('message')}")
    except BackendError as e:
        st.warning(f"模型状态获取失败：{e}")

    st.divider()
    st.subheader("会话")
    personas = client.list_personas()
    persona_opts = {p["id"]: p["name"] for p in personas}

    if st.button("✏️ 新建会话", use_container_width=True):
        try:
            conv = client.create_conversation(persona_id=personas[0]["id"])
            st.session_state.cid = conv["id"]
            st.rerun()
        except BackendError as e:
            st.error(str(e))

    convs = client.list_conversations()
    if not convs and "cid" not in st.session_state:
        conv = client.create_conversation(persona_id=personas[0]["id"])
        st.session_state.cid = conv["id"]
        st.rerun()

    for c in convs:
        c1, c2 = st.columns([5, 1])
        active = st.session_state.get("cid") == c["id"]
        with c1:
            if st.button(c["title"], key=f"cv_{c['id']}",
                         type="primary" if active else "secondary",
                         use_container_width=True):
                st.session_state.cid = c["id"]
                st.rerun()
        with c2:
            if st.button("🗑", key=f"del_{c['id']}"):
                client.delete_conversation(c["id"])
                if st.session_state.get("cid") == c["id"]:
                    st.session_state.cid = None
                st.rerun()

    st.divider()
    st.subheader("会话导出")
    if st.button("⬇️ 导出为 Markdown（后台任务）", use_container_width=True,
                 disabled=not st.session_state.get("cid")):
        try:
            job = client.create_export_job(st.session_state.cid)
            st.session_state.job_id = job["job_id"]
        except BackendError as e:
            st.error(str(e))

    if st.session_state.get("job_id"):
        with st.status("导出任务执行中…", expanded=True) as status:
            job = client.get_job(st.session_state.job_id)
            st.write(f"状态：{job['status']}")
            if job["status"] == "succeeded":
                md = job.get("result") or ""
                st.download_button("下载 .md", data=md,
                                  file_name=f"{st.session_state.cid}.md",
                                  mime="text/markdown")
                status.update(label="导出完成", state="complete")
            elif job["status"] == "failed":
                st.error(f"导出失败：{job.get('error')}")
                status.update(label="导出失败", state="error")
            else:
                time.sleep(0.5)
                st.rerun()

# ---------------- 主区 ----------------
if not st.session_state.get("cid"):
    st.info("请在左侧新建或选择一个会话。")
    st.stop()

st.title("🤖 AI 智能伴侣")

# 历史消息
msgs = client.list_messages(st.session_state.cid)
for m in msgs:
    if m["role"] == "file":
        st.info(m["content"][:200] + ("…" if len(m["content"]) > 200 else ""))
    else:
        with st.chat_message(m["role"]):
            st.write(m["content"])

# 上传文件作为上下文
with st.expander("📎 上传文本文件（.txt/.md，≤5MB）"):
    up = st.file_uploader("选择文件", type=["txt", "md"])
    if up is not None and st.button("读取并加入对话"):
        try:
            r = client.upload_file(st.session_state.cid, up.name, up.getvalue())
            st.success(f"已读取 {r['name']}（{r['chars']} 字）")
            st.rerun()
        except BackendError as e:
            st.error(str(e))

# 输入并流式发送
prompt = st.chat_input("说点什么…")
if prompt:
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        full = ""
        try:
            for ev in client.stream_message(st.session_state.cid, prompt):
                if ev["type"] == "delta":
                    full += ev["text"]
                    placeholder.write(full)
                elif ev["type"] == "error":
                    placeholder.error(f"⚠️ {ev['message']}")
                elif ev["type"] == "done":
                    placeholder.write(ev.get("text") or full)
        except BackendError as e:
            placeholder.error(f"⚠️ 请求失败：{e}")
    st.rerun()
