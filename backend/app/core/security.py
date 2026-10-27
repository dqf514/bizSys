"""密码哈希（bcrypt）与 JWT 签发/校验。"""

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, roles: list[str], perms: list[str]) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "typ": "access",
        "roles": roles,
        "perms": perms,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: int) -> tuple[str, str]:
    """返回 (token, jti)；jti 存 Redis 以便吊销。"""
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "typ": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.refresh_token_expire_days),
        "jti": jti,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), jti


def create_step_up_token(user_id: int, minutes: int = 5) -> str:
    """敏感操作二次验证 token（短时有效，typ=step_up，仅证明"刚验证过身份"，不含权限）。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "typ": "step_up",
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_mfa_pending_token(user_id: int, minutes: int = 5) -> tuple[str, str]:
    """MFA 待验证 token（typ=mfa_pending，仅证明"密码已通过、等待二次验证码"）。

    返回 (token, jti)；jti 存 Redis（mfa:{jti}=user_id），一次性使用、可随验证成功/失败作废。
    """
    now = datetime.now(UTC)
    jti = uuid.uuid4().hex
    payload = {
        "sub": str(user_id),
        "typ": "mfa_pending",
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
        "jti": jti,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm), jti


def decode_token(token: str, expect_type: str) -> dict:
    """解码并校验；失败抛 jwt 异常由调用方处理。

    带 aud 的 token（如门户 portal）在本函数下必然校验失败：PyJWT 在 token 含 aud
    而 decode 未给 audience 时抛 InvalidAudienceError —— 门户 token 无法混入内部体系。
    """
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    if payload.get("typ") != expect_type:
        raise jwt.InvalidTokenError("token type mismatch")
    return payload


def create_portal_token(partner_id: int) -> str:
    """门户合作方 token：typ=portal_access + aud=portal，与内部 access token 双向隔离。"""
    now = datetime.now(UTC)
    payload = {
        "sub": str(partner_id),
        "typ": "portal_access",
        "aud": "portal",
        "iat": now,
        "exp": now + timedelta(minutes=settings.portal_token_expire_minutes),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_portal_token(token: str) -> dict:
    """门户 token 专用解码：强制 audience=portal + typ 校验；内部 token（无 aud）在此同样失败。"""
    payload = jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm], audience="portal"
    )
    if payload.get("typ") != "portal_access":
        raise jwt.InvalidTokenError("token type mismatch")
    return payload
