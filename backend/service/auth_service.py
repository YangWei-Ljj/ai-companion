"""鉴权业务：注册/登录/令牌校验（stdlib pbkdf2，非生产级，仅本地演示）。"""
from __future__ import annotations

import uuid

from sqlalchemy import text

from backend.core import security
from backend.core.exceptions import (
    AuthInvalidError,
    ConflictError,
    TokenInvalidError,
)
from backend.infrastructure.db import get_engine


def _row_to_user(row) -> dict:
    m = row._mapping
    return {"id": m["id"], "username": m["username"],
            "display_name": m["display_name"]}


def register(username: str, password: str, display_name: str | None) -> dict:
    username = username.strip()
    with get_engine().begin() as conn:
        exists = conn.execute(
            text("SELECT id FROM users WHERE username=:u"), {"u": username}
        ).fetchone()
        if exists:
            raise ConflictError("该用户名已被注册")
        salt_hex, hash_hex = security.hash_password(password)
        uid = str(uuid.uuid4())
        now = security.utcnow_iso()
        token = security.generate_token()
        conn.execute(
            text(
                "INSERT INTO users(id,username,password_hash,password_salt,display_name,"
                "created_at,updated_at) VALUES (:id,:u,:ph,:ps,:dn,:ca,:ua)"
            ),
            {"id": uid, "u": username, "ph": hash_hex, "ps": salt_hex,
             "dn": display_name, "ca": now, "ua": now},
        )
        conn.execute(
            text(
                "INSERT INTO auth_tokens(id,user_id,token_hash,created_at,expires_at,revoked)"
                " VALUES (:id,:uid,:th,:ca,:ea,0)"
            ),
            {"id": str(uuid.uuid4()), "uid": uid, "th": security.hash_token(token),
             "ca": now, "ea": security.token_expiry_iso()},
        )
    return {"token": token,
            "user": {"id": uid, "username": username, "display_name": display_name}}


def login(username: str, password: str) -> dict:
    username = username.strip()
    with get_engine().connect() as conn:
        row = conn.execute(
            text("SELECT * FROM users WHERE username=:u"), {"u": username}
        ).fetchone()
    if not row:
        raise AuthInvalidError("用户名或密码错误")
    if not security.verify_password(password, row._mapping["password_salt"],
                                    row._mapping["password_hash"]):
        raise AuthInvalidError("用户名或密码错误")
    now = security.utcnow_iso()
    token = security.generate_token()
    with get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO auth_tokens(id,user_id,token_hash,created_at,expires_at,revoked)"
                " VALUES (:id,:uid,:th,:ca,:ea,0)"
            ),
            {"id": str(uuid.uuid4()), "uid": row._mapping["id"],
             "th": security.hash_token(token),
             "ca": now, "ea": security.token_expiry_iso()},
        )
    return {"token": token, "user": _row_to_user(row)}


def get_user_by_token(token: str) -> dict:
    th = security.hash_token(token)
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                "SELECT u.id, u.username, u.display_name, t.expires_at, t.revoked "
                "FROM auth_tokens t JOIN users u ON u.id = t.user_id "
                "WHERE t.token_hash=:th"
            ),
            {"th": th},
        ).fetchone()
    if not row:
        raise TokenInvalidError("token 无效")
    m = row._mapping
    if m["revoked"]:
        raise TokenInvalidError("token 已注销")
    if m["expires_at"] < security.utcnow_iso():
        raise TokenInvalidError("token 已过期，请重新登录")
    return {"id": m["id"], "username": m["username"],
            "display_name": m["display_name"]}
