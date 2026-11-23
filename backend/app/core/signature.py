"""电子签名 —— HMAC-SHA256 密码学绑定。

合规原则 2.4：「签名需绑定账号、证书或多因子认证，签名后记录锁定；
禁止代签、批量自动签、图片印章。」

设计要点：
- 密钥由 `settings.jwt_secret` 派生（SHA-256 + 域分隔前缀），与 `app/core/crypto.py`
  的配置加密密钥同源但**不同域**，避免密钥复用；
- 签名覆盖**固定字段序**的规范化串，字段缺失一律按空串处理（None 与 "" 不混淆），
  保证验签方按同一顺序重算即可；
- 比较用 `hmac.compare_digest`，避免时序侧信道。
"""

import hashlib
import hmac
import os
from collections.abc import Iterable

from app.core.config import settings

ALG = "HMAC-SHA256"
# 密钥版本：轮换 jwt_secret 后历史签名无法复算，靠版本号标记（见 docs/compliance-baseline.md）
KEY_VERSION = "v1"

# 访客 NDA 签名绑定字段（顺序即规范化顺序，不可随意调整）
NDA_FIELDS: tuple[str, ...] = (
    "biz_type",
    "nda_no",
    "visitor_name",
    "visitor_company",
    "id_no",
    "title",
    "signed_at",
    "signed_by_id",
    "signed_by_name",
    "signed_ip",
    "signature_sha256",
)

# 报告用章签名绑定字段
REPORT_SEAL_FIELDS: tuple[str, ...] = (
    "biz_type",
    "report_no",
    "task_item_id",
    "content_hash",
    "sealed_by_id",
    "sealed_by_name",
    "sealed_at",
)


def _key() -> bytes:
    return hashlib.sha256(f"bizsys:evidence-signature:{settings.jwt_secret}".encode()).digest()


def canonical(payload: dict[str, object], fields: Iterable[str]) -> str:
    """固定字段序的规范化串；末尾补换行避免拼接歧义。"""
    parts = [f"{name}={'' if payload.get(name) is None else payload.get(name)}" for name in fields]
    return "\n".join(parts) + "\n"


def sign(payload: dict[str, object], fields: Iterable[str]) -> str:
    msg = canonical(payload, fields).encode("utf-8")
    return hmac.new(_key(), msg, hashlib.sha256).hexdigest()


def verify(payload: dict[str, object], fields: Iterable[str], signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign(payload, fields), signature)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | None) -> str:
    """文件内容 sha256；文件不存在返回空串。"""
    if not path or not os.path.isfile(path):
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()
