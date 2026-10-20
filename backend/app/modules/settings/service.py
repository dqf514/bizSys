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
KEY_SITE_FAVICON = "site.favicon"
KEY_WECOM_ENABLED = "wecom.enabled"
KEY_WECOM_CORP_ID = "wecom.corp_id"
KEY_WECOM_AGENT_ID = "wecom.agent_id"
KEY_WECOM_SECRET = "wecom.secret"  # AES-GCM 加密落库，接口永不返回明文
KEY_WECOM_CALLBACK = "wecom.callback_url"

DEFAULT_SITE_NAME = "bizSys"
LOGO_URL = "/api/v1/public/logo"
FAVICON_URL = "/api/v1/public/favicon"

LOGO_ALLOWED_EXT = {"png", "jpg", "jpeg", "svg", "webp"}
LOGO_MAX_BYTES = 2 * 1024 * 1024  # 2MB
LOGO_CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "svg": "image/svg+xml",
    "webp": "image/webp",
}

FAVICON_ALLOWED_EXT = {"ico", "png"}
FAVICON_MAX_BYTES = 1024 * 1024  # 1MB
FAVICON_CONTENT_TYPES = {
    "ico": "image/x-icon",
    "png": "image/png",
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
    db.flush()  # SessionLocal autoflush=False：新建行需显式 flush 才能被同事务后续 SELECT 命中


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
        "faviconUrl": FAVICON_URL if get_value(db, KEY_SITE_FAVICON) else "",
        "wecom": {
            "enabled": enabled,
            "corpId": corp_id,
            "agentId": agent_id,
            "secretSet": bool(secret),
            "callbackUrl": get_value(db, KEY_WECOM_CALLBACK),
        },
    }


def branding_out(db: Session) -> dict:
    from app.modules.maintenance.service import KEY_SHOW_DEMO

    return {
        "siteName": get_value(db, KEY_SITE_NAME, DEFAULT_SITE_NAME),
        "logoUrl": LOGO_URL if get_value(db, KEY_SITE_LOGO) else "",
        "faviconUrl": FAVICON_URL if get_value(db, KEY_SITE_FAVICON) else "",
        "wecomEnabled": wecom_ready(db),
        "showDemoAccounts": get_value(db, KEY_SHOW_DEMO) == "1",
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


def _save_brand_file(
    db: Session,
    *,
    key: str,
    url: str,
    label: str,
    allowed_ext: set[str],
    max_bytes: int,
    filename: str,
    data: bytes,
    user_id: int,
) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in allowed_ext:
        exts = "/".join(sorted(allowed_ext))
        raise BizException(R.GENERIC_PARAM, f"不支持的{label}文件类型：{ext or '无扩展名'}（限 {exts}）")
    if not data:
        raise BizException(R.GENERIC_PARAM, "文件为空")
    if len(data) > max_bytes:
        raise BizException(R.GENERIC_PARAM, f"{label}文件超过大小上限 {max_bytes // 1024 // 1024}MB")
    rel = Path("branding") / f"{key.rsplit('.', 1)[-1]}-{uuid.uuid4().hex}.{ext}"
    dest = Path(settings.upload_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    # 清理旧文件（尽力而为）
    old = get_value(db, key)
    if old and old != str(rel):
        try:
            (Path(settings.upload_dir) / old).unlink(missing_ok=True)
        except OSError:
            pass
    set_value(db, key, str(rel), user_id, f"系统{label}文件相对路径")
    return url


def _brand_file(db: Session, key: str, content_types: dict[str, str], label: str) -> tuple[Path, str]:
    """返回 (文件路径, content_type)；未设置抛 404。"""
    rel = get_value(db, key)
    if not rel:
        raise BizException(R.GENERIC_NOT_FOUND, f"尚未上传{label}")
    dest = Path(settings.upload_dir) / rel
    if not dest.exists():
        raise BizException(R.GENERIC_NOT_FOUND, f"{label}文件已丢失")
    ext = dest.suffix.lstrip(".").lower()
    return dest, content_types.get(ext, "application/octet-stream")


def save_logo(db: Session, filename: str, data: bytes, user_id: int) -> str:
    return _save_brand_file(
        db,
        key=KEY_SITE_LOGO,
        url=LOGO_URL,
        label="Logo",
        allowed_ext=LOGO_ALLOWED_EXT,
        max_bytes=LOGO_MAX_BYTES,
        filename=filename,
        data=data,
        user_id=user_id,
    )


def logo_file(db: Session) -> tuple[Path, str]:
    return _brand_file(db, KEY_SITE_LOGO, LOGO_CONTENT_TYPES, "Logo")


def save_favicon(db: Session, filename: str, data: bytes, user_id: int) -> str:
    return _save_brand_file(
        db,
        key=KEY_SITE_FAVICON,
        url=FAVICON_URL,
        label="Favicon",
        allowed_ext=FAVICON_ALLOWED_EXT,
        max_bytes=FAVICON_MAX_BYTES,
        filename=filename,
        data=data,
        user_id=user_id,
    )


def favicon_file(db: Session) -> tuple[Path, str]:
    return _brand_file(db, KEY_SITE_FAVICON, FAVICON_CONTENT_TYPES, "Favicon")


def clear_favicon(db: Session, user_id: int) -> None:
    old = get_value(db, KEY_SITE_FAVICON)
    if old:
        try:
            (Path(settings.upload_dir) / old).unlink(missing_ok=True)
        except OSError:
            pass
    set_value(db, KEY_SITE_FAVICON, "", user_id, "恢复默认 Favicon")
