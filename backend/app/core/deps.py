"""FastAPI 依赖：当前用户 / 权限点校验。"""

import jwt as pyjwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.db import get_db
from app.core.exceptions import BizException
from app.core.security import decode_token
from app.modules.auth.models import User

SUPER_ROLE = "super"  # 超管角色码，绕过权限点


def _bearer(authorization: str | None) -> str:
    if not authorization:
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    return token


def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    token = _bearer(authorization)
    try:
        payload = decode_token(token, "access")
    except pyjwt.ExpiredSignatureError:
        raise BizException(R.AUTH_UNAUTHORIZED, "登录已过期", http_status=401) from None
    except pyjwt.InvalidTokenError:
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None

    user = db.get(User, int(payload["sub"]))
    if not user or user.deleted:
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    if user.status == "locked":
        raise BizException(R.AUTH_LOCKED, http_status=401)
    if user.status != "enabled":
        raise BizException(R.AUTH_FORBIDDEN, http_status=403)
    return user


def user_perms(user: User, db: Session) -> set[str]:
    """权限点集合（带 token 缓存 + 数据库兜底刷新）。"""
    return set(user.perm_codes)


def require_perm(code: str):
    """权限依赖工厂：require_perm('contract:create')。超管角色绕过。"""

    def _checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if SUPER_ROLE in user.role_codes:
            return user
        if code in user.perm_codes:
            return user
        raise BizException(R.AUTH_FORBIDDEN, f"缺少权限：{code}", http_status=403)

    return _checker


def require_any_perm(*codes: str):
    """任一权限点满足即可（如菜单树同时服务菜单管理与角色授权两个入口）。超管角色绕过。"""

    def _checker(
        user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if SUPER_ROLE in user.role_codes:
            return user
        if any(code in user.perm_codes for code in codes):
            return user
        raise BizException(R.AUTH_FORBIDDEN, f"缺少权限：{'|'.join(codes)}", http_status=403)

    return _checker
