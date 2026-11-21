"""系统设置业务：sys_config 读写 / 品牌信息 / Logo / 企微凭据。

F5 新增**类型化开关**读取（``flag`` / ``number`` / ``text``）：
系统里原先并存三套布尔语义（``== "1"`` / ``!= "0"`` / 字符串空判），
新代码统一走 ``flag()``，避免"配了 0 还当成开启"这类线上事故。
"""

import time
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
    invalidate_switch(key)


# ---------------- 类型化开关（F5） ----------------

# 开关读取缓存：命中则免一次 SELECT。写入路径（set_value）会主动失效，
# 因此不存在"改了配置还要等缓存过期"的问题；缓存 miss 不写入（新建配置立即可见）。
_SWITCH_TTL_SECONDS = 30.0
_switch_cache: dict[str, tuple[float, str]] = {}

_TRUE_VALUES = {"1", "true", "yes", "on", "y", "t", "enabled"}
_FALSE_VALUES = {"0", "false", "no", "off", "n", "f", "disabled"}


def invalidate_switch(key: str | None = None) -> None:
    """失效开关缓存（key=None 全清）。"""
    if key is None:
        _switch_cache.clear()
    else:
        _switch_cache.pop(key, None)


def _raw_value(db: Session, key: str) -> str | None:
    """读原始配置值（带短缓存）；不存在返回 None。"""
    hit = _switch_cache.get(key)
    now = time.monotonic()
    if hit and now - hit[0] < _SWITCH_TTL_SECONDS:
        return hit[1]
    row = db.scalar(select(SysConfig).where(SysConfig.key == key, SysConfig.deleted == 0))
    if row is None:
        return None
    value = row.value or ""
    _switch_cache[key] = (now, value)
    return value


def to_bool(raw: str, default: bool = True) -> bool:
    """把配置字符串解析成布尔。未知取值返回 default（而不是当成 False）。"""
    v = (raw or "").strip().lower()
    if not v:
        return default
    if v in _TRUE_VALUES:
        return True
    if v in _FALSE_VALUES:
        return False
    return default


def flag(db: Session, key: str, default: bool = True) -> bool:
    """布尔开关。缺失或取值无法识别时返回 default。"""
    raw = _raw_value(db, key)
    if raw is None:
        return default
    return to_bool(raw, default)


def number(db: Session, key: str, default: float = 0.0) -> float:
    """数值开关 / 参数。取值非法时返回 default。"""
    raw = _raw_value(db, key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw.strip())
    except (TypeError, ValueError):
        return default


def text(db: Session, key: str, default: str = "") -> str:
    """文本配置。缺失时返回 default。"""
    raw = _raw_value(db, key)
    if raw is None:
        return default
    return raw


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
        "messaging": messaging_out(db),
        "ai": ai_out(db),
    }


# ---------------- AI 集成（OpenAI 兼容） ----------------


def ai_out(db: Session) -> dict:
    """AI 配置回显：api_key 只回 apiKeySet 布尔，不回明文。"""
    from app.services import ai

    cfg = ai.ai_config(db)
    return {
        "enabled": cfg["enabled"],
        "baseUrl": cfg["base_url"],
        "apiKeySet": bool(cfg["api_key"]),
        "model": cfg["model"],
        "visionModel": cfg["vision_model"],
        "timeout": cfg["timeout"],
    }


def _update_ai(db: Session, a, user_id: int) -> None:
    from app.services import ai

    if a.base_url.strip() and not a.base_url.strip().startswith(("http://", "https://")):
        raise BizException(R.GENERIC_PARAM, "AI 端点 URL 须以 http(s):// 开头")
    set_value(db, ai.KEY_AI_ENABLED, "1" if a.enabled else "0", user_id, "AI 总开关")
    set_value(db, ai.KEY_AI_BASE_URL, a.base_url.strip(), user_id, "AI 端点（OpenAI 兼容）")
    set_value(db, ai.KEY_AI_MODEL, a.model.strip(), user_id, "AI 模型名")
    set_value(db, ai.KEY_AI_VISION_MODEL, a.vision_model.strip(), user_id, "AI 多模态模型名")
    set_value(db, ai.KEY_AI_TIMEOUT, str(a.timeout), user_id, "AI 超时秒数")
    if a.api_key:  # 空 = 不修改
        set_value(db, ai.KEY_AI_API_KEY, encrypt_text(a.api_key.strip()), user_id, "AI API Key（加密）")


# ---------------- 消息通道（邮件 SMTP / 短信） ----------------


def _secret_set(db: Session, key: str) -> bool:
    """密文键是否已设置（接口只回布尔，不回明文）。"""
    return bool(get_value(db, key))


def messaging_out(db: Session) -> dict:
    """消息通道配置回显：密文键只回 xxxSet 布尔。"""
    from app.modules.settings import notify

    cfg_email = notify.email_config(db)
    cfg_sms = notify.sms_config(db)
    return {
        "email": {
            "host": cfg_email["host"],
            "port": cfg_email["port"],
            "security": cfg_email["security"],
            "username": cfg_email["username"],
            "passwordSet": bool(cfg_email["password"]),
            "sender": cfg_email["sender"],
        },
        "sms": {
            "provider": cfg_sms["provider"],
            "aliyun": {
                "accessKeyId": cfg_sms["aliyun"]["access_key_id"],
                "accessKeySecretSet": bool(cfg_sms["aliyun"]["access_key_secret"]),
                "signName": cfg_sms["aliyun"]["sign_name"],
                "templateCode": cfg_sms["aliyun"]["template_code"],
            },
            "tencent": {
                "secretId": cfg_sms["tencent"]["secret_id"],
                "secretKeySet": bool(cfg_sms["tencent"]["secret_key"]),
                "sdkAppId": cfg_sms["tencent"]["sdk_app_id"],
                "signName": cfg_sms["tencent"]["sign_name"],
                "templateId": cfg_sms["tencent"]["template_id"],
            },
            "huawei": {
                "appKey": cfg_sms["huawei"]["app_key"],
                "appSecretSet": bool(cfg_sms["huawei"]["app_secret"]),
                "sender": cfg_sms["huawei"]["sender"],
                "templateId": cfg_sms["huawei"]["template_id"],
            },
            "customHttp": {
                "url": cfg_sms["custom_http"]["url"],
                "paramTemplate": cfg_sms["custom_http"]["param_template"],
                "authHeaderSet": bool(cfg_sms["custom_http"]["auth_header"]),
            },
        },
    }


def _update_messaging(db: Session, m, user_id: int) -> None:
    from app.modules.settings import notify

    if m.email is not None:
        e = m.email
        set_value(db, notify.KEY_EMAIL_HOST, e.host.strip(), user_id, "SMTP 主机")
        set_value(db, notify.KEY_EMAIL_PORT, str(e.port), user_id, "SMTP 端口")
        set_value(db, notify.KEY_EMAIL_SECURITY, e.security, user_id, "SMTP 安全模式")
        set_value(db, notify.KEY_EMAIL_USERNAME, e.username.strip(), user_id, "SMTP 用户名")
        set_value(db, notify.KEY_EMAIL_SENDER, e.sender.strip(), user_id, "邮件发件人")
        if e.password:  # 空 = 不修改
            set_value(db, notify.KEY_EMAIL_PASSWORD, encrypt_text(e.password.strip()), user_id, "SMTP 密码（加密）")
    if m.sms is not None:
        s = m.sms
        set_value(db, notify.KEY_SMS_PROVIDER, s.provider, user_id, "短信服务商")
        if s.aliyun is not None:
            set_value(db, notify.KEY_SMS_ALIYUN_AK_ID, s.aliyun.access_key_id.strip(), user_id, "阿里云 AK ID")
            set_value(db, notify.KEY_SMS_ALIYUN_SIGN, s.aliyun.sign_name.strip(), user_id, "阿里云短信签名")
            set_value(db, notify.KEY_SMS_ALIYUN_TEMPLATE, s.aliyun.template_code.strip(), user_id, "阿里云短信模板")
            if s.aliyun.access_key_secret:
                set_value(db, notify.KEY_SMS_ALIYUN_AK_SECRET, encrypt_text(s.aliyun.access_key_secret.strip()),
                          user_id, "阿里云 AK Secret（加密）")
        if s.tencent is not None:
            set_value(db, notify.KEY_SMS_TENCENT_SECRET_ID, s.tencent.secret_id.strip(), user_id, "腾讯云 SecretId")
            set_value(db, notify.KEY_SMS_TENCENT_APP_ID, s.tencent.sdk_app_id.strip(), user_id, "腾讯云 SdkAppId")
            set_value(db, notify.KEY_SMS_TENCENT_SIGN, s.tencent.sign_name.strip(), user_id, "腾讯云短信签名")
            set_value(db, notify.KEY_SMS_TENCENT_TEMPLATE, s.tencent.template_id.strip(), user_id, "腾讯云短信模板")
            if s.tencent.secret_key:
                set_value(db, notify.KEY_SMS_TENCENT_SECRET_KEY, encrypt_text(s.tencent.secret_key.strip()),
                          user_id, "腾讯云 SecretKey（加密）")
        if s.huawei is not None:
            set_value(db, notify.KEY_SMS_HUAWEI_APP_KEY, s.huawei.app_key.strip(), user_id, "华为云 AppKey")
            set_value(db, notify.KEY_SMS_HUAWEI_SENDER, s.huawei.sender.strip(), user_id, "华为云短信通道号")
            set_value(db, notify.KEY_SMS_HUAWEI_TEMPLATE, s.huawei.template_id.strip(), user_id, "华为云短信模板")
            if s.huawei.app_secret:
                set_value(db, notify.KEY_SMS_HUAWEI_APP_SECRET, encrypt_text(s.huawei.app_secret.strip()),
                          user_id, "华为云 AppSecret（加密）")
        if s.custom_http is not None:
            c = s.custom_http
            if c.url.strip() and not c.url.strip().startswith(("http://", "https://")):
                raise BizException(R.GENERIC_PARAM, "自定义短信网关 URL 须以 http(s):// 开头")
            set_value(db, notify.KEY_SMS_CUSTOM_URL, c.url.strip(), user_id, "自定义短信网关 URL")
            set_value(db, notify.KEY_SMS_CUSTOM_TEMPLATE, c.param_template.strip(), user_id, "自定义短信参数模板")
            if c.auth_header:
                set_value(db, notify.KEY_SMS_CUSTOM_AUTH, encrypt_text(c.auth_header.strip()),
                          user_id, "自定义短信网关鉴权头（加密）")


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
    if body.messaging is not None:
        _update_messaging(db, body.messaging, user_id)
    if body.ai is not None:
        _update_ai(db, body.ai, user_id)
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
