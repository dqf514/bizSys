"""敏感数据脱敏：AI 网关出网 prompt 前的统一掩码层。

级别（sys_config ai.masking.level，缺省 standard）：
- off      不脱敏（含个人信息场景除外，见 PERSONAL_FEATURES，强制按 standard 处理）
- standard 掩码手机号/身份证号/银行卡号/邮箱
- strict   在 standard 基础上追加税号掩码 + 客户名称替换为代号（客户#N）

掩码只作用于发给 AI 的 prompt 文本，不改库内数据；用量日志记录实际生效级别。
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.settings.service import get_value

KEY_MASKING_LEVEL = "ai.masking.level"

LEVELS = ("off", "standard", "strict")
DEFAULT_LEVEL = "standard"

# 涉及个人信息/敏感运营数据的功能：即使级别为 off 也强制按 standard 脱敏
PERSONAL_FEATURES = frozenset({"hr_prefill", "oa_prefill", "flow_anomaly", "daily_digest", "assistant", "knowledge"})

_MASK = "**********"

_RE_ID_CARD = re.compile(r"(?<![0-9A-Za-z])\d{17}[\dXx](?![0-9A-Za-z])")
_RE_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
# 银行卡号 13-19 位连续数字（须在身份证/手机号之后执行，避免重复匹配）
_RE_BANK_CARD = re.compile(r"(?<![\d*])\d{13,19}(?![\d*])")
_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# 税号：15-20 位大写字母数字组合且至少含一个字母（纯数字长串已由银行卡规则处理）
_RE_TAX_NO = re.compile(r"(?<![0-9A-Za-z])(?=[0-9A-Z]*[A-Z])(?=[0-9A-Z]{15,20}(?![0-9A-Za-z]))[0-9A-Z]{15,20}")

# strict 客户名替换：只处理长度足够的名称，长名优先避免子串误替换
_CUSTOMER_MIN_LEN = 4
_CUSTOMER_LIMIT = 500


def configured_level(db: Session) -> str:
    raw = (get_value(db, KEY_MASKING_LEVEL) or "").strip().lower()
    return raw if raw in LEVELS else DEFAULT_LEVEL


def effective_level(db: Session, feature: str) -> str:
    """实际生效级别：off 时个人信息场景仍强制 standard。"""
    level = configured_level(db)
    if level == "off" and feature in PERSONAL_FEATURES:
        return "standard"
    return level


def _customer_aliases(db: Session) -> dict[str, str]:
    """启用客户名称 → 代号 客户#N（按 id 排序稳定编号）。"""
    from app.modules.crm.models import Customer

    rows = db.scalars(
        select(Customer.name)
        .where(Customer.deleted == 0, Customer.status == "enabled")
        .order_by(Customer.id)
        .limit(_CUSTOMER_LIMIT)
    ).all()
    names = sorted({n.strip() for n in rows if n and len(n.strip()) >= _CUSTOMER_MIN_LEN}, key=len, reverse=True)
    return {name: f"客户#{i + 1}" for i, name in enumerate(names)}


def mask_text(text: str, level: str, db: Session | None = None) -> str:
    """按级别掩码文本。level=off 原样返回；strict 客户代号替换需要 db（查客户清单）。"""
    if not text or level == "off":
        return text
    text = _RE_ID_CARD.sub(_MASK * 2, text)
    text = _RE_PHONE.sub("1**********", text)
    text = _RE_BANK_CARD.sub(_MASK, text)
    text = _RE_EMAIL.sub("***@***", text)
    if level == "strict":
        text = _RE_TAX_NO.sub(_MASK * 2, text)
        if db is not None:
            for name, alias in _customer_aliases(db).items():
                text = text.replace(name, alias)
    return text


def mask_messages(messages: list[dict], level: str, db: Session | None = None) -> list[dict]:
    """掩码 chat messages：字符串 content 与多模态 parts 中的 text 片段。"""
    if level == "off":
        return messages
    out = []
    for m in messages:
        m = dict(m)
        content = m.get("content")
        if isinstance(content, str):
            m["content"] = mask_text(content, level, db)
        elif isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("type") == "text":
                    p = dict(p)
                    p["text"] = mask_text(str(p.get("text") or ""), level, db)
                parts.append(p)
            m["content"] = parts
        out.append(m)
    return out
