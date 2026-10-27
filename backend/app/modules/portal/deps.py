"""门户依赖：当前合作方账号（与内部 get_current_user 完全隔离）。"""

import jwt as pyjwt
from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.db import get_db
from app.core.exceptions import BizException
from app.core.security import decode_portal_token
from app.modules.portal.models import PartnerUser


def get_current_partner(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> PartnerUser:
    if not authorization:
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    try:
        payload = decode_portal_token(token)
    except pyjwt.ExpiredSignatureError:
        raise BizException(R.AUTH_UNAUTHORIZED, "登录已过期", http_status=401) from None
    except pyjwt.InvalidTokenError:
        # 内部 access token（无 aud）在这里也会校验失败 —— 双向隔离
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None

    partner = db.get(PartnerUser, int(payload["sub"]))
    if not partner or partner.deleted or partner.status != "enabled":
        raise BizException(R.AUTH_UNAUTHORIZED, http_status=401) from None
    return partner


def get_optional_partner(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> PartnerUser | None:
    """公开页面（公告列表/详情）可选登录：无/无效 token 一律按匿名处理，不抛 401。"""
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = decode_portal_token(token)
    except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
        return None
    partner = db.get(PartnerUser, int(payload["sub"]))
    if not partner or partner.deleted or partner.status != "enabled":
        return None
    return partner
