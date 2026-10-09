"""企业微信扫码登录（技术设计 §9.1）：/api/v1/auth/wecom/*。

凭据来自系统设置（sys_config，Secret 加密存储）；本文件只新增端点，不动现有 login/refresh 逻辑。
无真实企微凭据，sso_userid 兑换链路未实测（联调后移除本说明）。
"""

import uuid
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.config import settings
from app.core.db import get_db
from app.core.exceptions import BizException
from app.core.redis import get_redis
from app.core.route import EnvelopeRoute
from app.core.security import create_access_token, create_refresh_token
from app.modules.auth import service as auth_svc
from app.modules.auth.models import User
from app.modules.integration.adapters import ADAPTERS, WecomAdapter
from app.modules.settings import service as settings_svc
from app.modules.settings.schemas import WecomCallbackIn

router = APIRouter(prefix="/auth/wecom", tags=["auth"], route_class=EnvelopeRoute)

STATE_KEY = "wecom:state:{state}"
STATE_TTL_SEC = 10 * 60
QR_CONNECT_URL = "https://open.work.weixin.qq.com/wwopen/sso/qrConnect"


def _adapter() -> WecomAdapter:
    return ADAPTERS["wecom"]  # type: ignore[return-value]


@router.get("/qr-url")
def qr_url(
    redirect_uri: str = Query(default="", max_length=255),
    db: Session = Depends(get_db),
):
    """免登录：构造企微扫码页 URL（state 存 Redis 防 CSRF，一次性，10 分钟有效）。"""
    enabled, corp_id, agent_id, _secret = settings_svc.wecom_creds(db)
    if not (enabled and corp_id and agent_id and _secret):
        raise BizException(R.ADAPTER_NOT_CONFIGURED, "企业微信登录未启用或未配置完整")
    redirect = redirect_uri or settings_svc.get_value(db, settings_svc.KEY_WECOM_CALLBACK)
    if not redirect:
        raise BizException(R.GENERIC_PARAM, "缺少 redirect_uri（且未配置默认回调 URL）")
    state = uuid.uuid4().hex
    get_redis().setex(STATE_KEY.format(state=state), STATE_TTL_SEC, "1")
    url = (
        f"{QR_CONNECT_URL}?appid={quote(corp_id)}&agentid={quote(agent_id)}"
        f"&redirect_uri={quote(redirect, safe='')}&state={state}"
    )
    return {"url": url, "state": state}


@router.post("/callback")
def callback(body: WecomCallbackIn, request: Request, db: Session = Depends(get_db)):
    """扫码回调：code 换企微 userid → sys_user.wecom_userid 映射本地账号 → 签发自有 JWT。"""
    r = get_redis()
    state_key = STATE_KEY.format(state=body.state)
    if not r.get(state_key):
        raise BizException(R.AUTH_WECOM_STATE_INVALID, http_status=401)
    r.delete(state_key)  # 一次性

    enabled, corp_id, agent_id, secret = settings_svc.wecom_creds(db)
    if not (enabled and corp_id and agent_id and secret):
        raise BizException(R.ADAPTER_NOT_CONFIGURED, "企业微信登录未启用或未配置完整")

    userid = _adapter().sso_userid(corp_id, secret, body.code)

    user = db.query(User).filter(User.wecom_userid == userid, User.deleted == 0).first()
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    if not user:
        auth_svc._login_log(db, userid, 0, reason="企微账号未绑定", ip=ip, ua=ua)
        db.commit()
        raise BizException(R.AUTH_WECOM_NOT_BOUND, f"企微账号 {userid} 未绑定本地用户")
    if user.status != "enabled":
        auth_svc._login_log(db, user.username, 0, reason=user.status, ip=ip, ua=ua)
        db.commit()
        raise BizException(R.AUTH_FORBIDDEN, http_status=401)

    # 与 /auth/login 返回结构一致
    user.last_login_at = datetime.now()
    access = create_access_token(user.id, user.role_codes, user.perm_codes)
    refresh, jti = create_refresh_token(user.id)
    r.setex(f"refresh:{jti}", 60 * 60 * 24 * settings.refresh_token_expire_days, str(user.id))
    audit(db, user_id=user.id, module="auth", action="wecom_login", detail={"wecom_userid": userid}, ip=ip)
    auth_svc._login_log(db, user.username, 1, ip=ip, ua=ua)
    db.commit()
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "Bearer",
        "user": auth_svc._user_out(db, user),
    }
