"""本地演示级安全原语（非生产级，仅本地演示）。

- 密码：``hashlib.pbkdf2_hmac``（标准库，禁止引入 passlib/jose）；
- 令牌：``secrets.token_urlsafe`` 不透明 token，库内仅存 SHA-256 哈希；
- 时间统一 UTC ISO8601。
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from backend.core.config import settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    return utcnow().isoformat(timespec="seconds")


def hash_password(password: str) -> tuple[str, str]:
    """返回 (salt_hex, hash_hex)。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, settings.PBKDF2_ITERATIONS
    )
    return salt.hex(), dk.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex),
        settings.PBKDF2_ITERATIONS,
    )
    return hmac.compare_digest(dk.hex(), hash_hex)


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_expiry_iso() -> str:
    return (utcnow() + timedelta(hours=settings.TOKEN_TTL_HOURS)).isoformat(
        timespec="seconds"
    )
