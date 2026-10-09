"""系统设置业务：sys_config 读写 / 品牌信息 / Logo / 企微凭据。"""

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.config import settings
from app.core.crypto import decrypt_text, encrypt_text
from app.core.exceptions import BizException
from app.modules.settings.models import SysConfig

# ---- 配置键 ----
KEY_SITE_NAME = "site.name"
KEY_SITE_LOGO = "site.logo"
KEY_WECOM_ENABLED = "wecom.enabled"
KEY_WECOM_CORP_ID = "wecom.corp_id"
KEY_WECOM_AGENT_ID = "wecom.agent_id"
KEY_WECOM_SECRET = "wecom.secret"  # AES-GCM 加密落库，接口永不返回明文
KEY_WECOM_CALLBACK = "wecom.callback_url"

DEFAULT_SITE_NAME = "bizSys"
LOGO_URL = "/api/v1/public/logo"

LOGO_ALLOWED_EXT = {"png", "jpg", "jpeg", "svg", "webp"}
LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2MB
LOGO_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}


def get_value(db: Session, key: str, default: str = "") -> str:
    row = db.scalar(select(SysConfig).where(SysConfig.key == key, SysConfig.deleted == 0))
    return row.value if row and row.value else default


def set_value(db: Session, key: str, value: str, user_id: int | None = None, remark: str = "") -> None:
    row = db.scalar(select(SysConfig).where(SysConfig.key == key, SysConfig.deleted == 0))
    if row is None:
        db.add(SysConfig(key=key, value=value, remark=remark, create_by=user_id))
    else:
        row.value = value
        row.update_by = user_id


def wecom_creds(db: Session) -> tuple[bool, str, str, str]:
    """返回 (enabled, corp_id, agent_id, secret 明文)。"""
    enabled = get_value(db, KEY_WECOM_ENABLED) == "1"
    corp_id = get_value(db, KEY_WECOM_CORP_ID)
    agent_id = get_value(db, KEY_WECOM_AGENT_ID)
    secret = decrypt_text(get_value(db, KEY_WECOM_SECRET)) if get_value(db, KEY_WECOM_SECRET) else ""
    return enabled, corp_id, agent_id, secret


def wecom_ready(db: Session) -> bool:
    enabled, corp_id, agent_id, secret = wecom_creds(db)
    return enabled and bool(corp_id) and bool(agent_id) and bool(secret)


def settings_out(db: Session) -> dict:
    enabled, corp_id, agent_id, secret = wecom_creds(db)
    return {
        "siteName": get_value(db, KEY_SITE_NAME, DEFAULT_SITE_NAME),
        "logoUrl": LOGO_URL if get_value(db, KEY_SITE_LOGO) else "",
        "wecom": {
            "enabled": enabled,
            "corpId": corp_id,
            "agentId": agent_id,
            "secretSet": bool(secret),
            "callbackUrl": get_value(db, KEY_WECOM_CALLBACK),
        },
    }


def branding_out(db: Session) -> dict:
    return {
        "siteName": get_value(db, KEY_SITE_NAME, DEFAULT_SITE_NAME),
        "logoUrl": LOGO_URL if get_value(db, KEY_SITE_LOGO) else "",
        "wecomEnabled": wecom_ready(db),
    }


def update_settings(db: Session, body, user_id: int) -> dict:
    if body.site_name is not None:
        name = body.site_name.strip()
        if not name:
            raise BizException(R.GENERIC_PARAM, "系统名称不能为空")
        set_value(db, KEY_SITE_NAME, name, user_id, "系统名称")
    if body.wecom is not None:
        w = body.wecom
        set_value(db, KEY_WECOM_ENABLED, "1" if w.enabled else "0", user_id, "企微登录开关")
        set_value(db, KEY_WECOM_CORP_ID, w.corp_id.strip(), user_id, "企微 CorpId")
        set_value(db, KEY_WECOM_AGENT_ID, w.agent_id.strip(), user_id, "企微 AgentId")
        set_value(db, KEY_WECOM_CALLBACK, w.callback_url.strip(), user_id, "企微回调 URL")
        if w.secret:  # 空 = 不修改
            set_value(db, KEY_WECOM_SECRET, encrypt_text(w.secret.strip()), user_id, "企微 Secret（加密）")
    return settings_out(db)


def save_logo(db: Session, filename: str, data: bytes, user_id: int) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in LOGO_ALLOWED_EXT:
        raise BizException(R.GENERIC_PARAM, f"不支持的 Logo 文件类型：{ext or '无扩展名'}（限 png/jpg/svg/webp）")
    if not data:
        raise BizException(R.GENERIC_PARAM, "文件为空")
    if len(data) > LOGO_MAX_BYTES:
        raise BizException(R.GENERIC_PARAM, "Logo 文件超过大小上限 2MB")
    rel = Path("branding") / f"logo-{uuid.uuid4().hex}.{ext}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    # 清理旧 Logo 文件（尽力而为）
    old = get_value(db, KEY_SITE_LOGO)
    if old and old != str(rel):
        try:
            (Path(settings.upload_dir) / old).unlink(missing_ok=True)
        except OSError:
            pass
    set_value(db, KEY_SITE_LOGO, str(rel), user_id, "系统 Logo 文件相对路径")
    return LOGO_URL


def logo_file(db: Session) -> tuple[Path, str]:
    """返回 (文件路径, content_type)；未设置抛 404。"""
    rel = get_value(db, KEY_SITE_LOGO)
    if not rel:
        raise BizException(R.GENERIC_NOT_FOUND, "尚未上传 Logo")
    dest = Path(settings.upload_dir) / rel
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, "Logo 文件已丢失")
    ext = dest.suffix.lstrip(".").lower()
    return dest, LOGO_CONTENT_TYPES.get(ext, "application/octet-stream")
