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
    return derive_key("config-secret")


def derive_key(domain: str) -> bytes:
    """从 jwt_secret 派生带域分隔的子密钥。

    不同用途用不同 domain，避免同一密钥被跨用途复用（配置密文 / 电子签名 / 审计链）。
    """
    return hashlib.sha256(f"bizsys:{domain}:{settings.jwt_secret}".encode()).digest()


def encrypt_text_domain(domain: str, plain: str) -> str:
    """按 domain 派生子密钥做 AES-GCM 加密（B10-1 员工证件号等敏感个人信息）。

    与 `encrypt_text` 的区别只在密钥来源：**必须用不同 domain**，否则同一密钥
    会跨用途复用（配置密文 / 员工证件号 / 电子签名 / 审计链）。
    """
    nonce = os.urandom(12)
    ct = AESGCM(derive_key(domain)).encrypt(nonce, plain.encode("utf-8"), None)
    return _PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii")


def decrypt_text_domain(domain: str, value: str) -> str:
    """`encrypt_text_domain` 的逆运算；非 `enc:` 前缀的值按明文兼容返回。"""
    if not value.startswith(_PREFIX):
        return value
    raw = base64.urlsafe_b64decode(value[len(_PREFIX) :])
    return AESGCM(derive_key(domain)).decrypt(raw[:12], raw[12:], None).decode("utf-8")


def encrypt_text(plain: str) -> str:
    return encrypt_text_domain("config-secret", plain)


def decrypt_text(value: str) -> str:
    return decrypt_text_domain("config-secret", value)
