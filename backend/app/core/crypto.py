"""配置敏感值对称加密（AES-GCM）。

密钥由 settings.jwt_secret 派生（SHA-256，带域分隔前缀），不单独维护密钥文件；
密文格式 ``enc:<base64url(nonce + ciphertext)>``，非 enc: 前缀的值按明文兼容返回。
"""

import base64
import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_PREFIX = "enc:"


def _key() -> bytes:
    return hashlib.sha256(f"bizsys:config-secret:{settings.jwt_secret}".encode()).digest()


def encrypt_text(plain: str) -> str:
    nonce = os.urandom(12)
    ct = AESGCM(_key()).encrypt(nonce, plain.encode("utf-8"), None)
    return _PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt_text(value: str) -> str:
    if not value.startswith(_PREFIX):
        return value
    raw = base64.urlsafe_b64decode(value[len(_PREFIX) :])
    return AESGCM(_key()).decrypt(raw[:12], raw[12:], None).decode("utf-8")
