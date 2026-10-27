"""消息通道：邮件 SMTP / 短信（阿里云/腾讯云/华为云预设 + 自定义 HTTP 网关）。

配置存 sys_config（msg.* 键），密文一律 AES-GCM 加密落库、接口不回明文。
发送能力现状：
- 邮件：smtplib 真实发送（ssl / starttls / none）；
- 短信 custom_http：urllib 真实 POST，参数模板用 {phone}/{code} 占位；
- 短信阿里云/腾讯云/华为云：预设字段落库 + 结构校验，厂商网关签名未联调（遗留项）；
- 任何通道未配置/未联调：非生产环境（ENV != prod）降级为调试通道（写日志、调用方回显 debugCode），
  生产环境直接报错，绝不回显验证码。
"""

import json
import logging
import smtplib
import urllib.request
from email.message import EmailMessage
from email.utils import formataddr, parseaddr

from sqlalchemy.orm import Session

from app.core import response as R
from app.core.config import settings
from app.core.crypto import decrypt_text
from app.core.exceptions import BizException
from app.modules.settings.service import get_value

logger = logging.getLogger("bizsys")

# ---- 配置键 ----
KEY_EMAIL_HOST = "msg.email.host"
KEY_EMAIL_PORT = "msg.email.port"
KEY_EMAIL_SECURITY = "msg.email.security"  # ssl | starttls | none
KEY_EMAIL_USERNAME = "msg.email.username"
KEY_EMAIL_PASSWORD = "msg.email.password"  # AES-GCM 加密
KEY_EMAIL_SENDER = "msg.email.sender"

KEY_SMS_PROVIDER = "msg.sms.provider"  # aliyun | tencent | huawei | custom_http
KEY_SMS_ALIYUN_AK_ID = "msg.sms.aliyun.access_key_id"
KEY_SMS_ALIYUN_AK_SECRET = "msg.sms.aliyun.access_key_secret"  # AES-GCM 加密
KEY_SMS_ALIYUN_SIGN = "msg.sms.aliyun.sign_name"
KEY_SMS_ALIYUN_TEMPLATE = "msg.sms.aliyun.template_code"
KEY_SMS_TENCENT_SECRET_ID = "msg.sms.tencent.secret_id"
KEY_SMS_TENCENT_SECRET_KEY = "msg.sms.tencent.secret_key"  # AES-GCM 加密
KEY_SMS_TENCENT_APP_ID = "msg.sms.tencent.sdk_app_id"
KEY_SMS_TENCENT_SIGN = "msg.sms.tencent.sign_name"
KEY_SMS_TENCENT_TEMPLATE = "msg.sms.tencent.template_id"
KEY_SMS_HUAWEI_APP_KEY = "msg.sms.huawei.app_key"
KEY_SMS_HUAWEI_APP_SECRET = "msg.sms.huawei.app_secret"  # AES-GCM 加密
KEY_SMS_HUAWEI_SENDER = "msg.sms.huawei.sender"
KEY_SMS_HUAWEI_TEMPLATE = "msg.sms.huawei.template_id"
KEY_SMS_CUSTOM_URL = "msg.sms.custom.url"
KEY_SMS_CUSTOM_TEMPLATE = "msg.sms.custom.param_template"
KEY_SMS_CUSTOM_AUTH = "msg.sms.custom.auth_header"  # AES-GCM 加密

SMS_PROVIDERS = ("aliyun", "tencent", "huawei", "custom_http")
EMAIL_SECURITY_MODES = ("ssl", "starttls", "none")

_HTTP_TIMEOUT_SEC = 10


def _decrypted(db: Session, key: str) -> str:
    raw = get_value(db, key)
    return decrypt_text(raw) if raw else ""


def email_config(db: Session) -> dict:
    """邮件通道配置（password 为解密明文，仅限服务端内部使用）。"""
    security = get_value(db, KEY_EMAIL_SECURITY) or "ssl"
    if security not in EMAIL_SECURITY_MODES:
        security = "ssl"
    port_raw = get_value(db, KEY_EMAIL_PORT)
    return {
        "host": get_value(db, KEY_EMAIL_HOST),
        "port": int(port_raw) if port_raw.isdigit() else 0,
        "security": security,
        "username": get_value(db, KEY_EMAIL_USERNAME),
        "password": _decrypted(db, KEY_EMAIL_PASSWORD),
        "sender": get_value(db, KEY_EMAIL_SENDER),
    }


def sms_config(db: Session) -> dict:
    """短信通道配置（密钥为解密明文，仅限服务端内部使用）。"""
    provider = get_value(db, KEY_SMS_PROVIDER)
    if provider not in SMS_PROVIDERS:
        provider = ""
    return {
        "provider": provider,
        "aliyun": {
            "access_key_id": get_value(db, KEY_SMS_ALIYUN_AK_ID),
            "access_key_secret": _decrypted(db, KEY_SMS_ALIYUN_AK_SECRET),
            "sign_name": get_value(db, KEY_SMS_ALIYUN_SIGN),
            "template_code": get_value(db, KEY_SMS_ALIYUN_TEMPLATE),
        },
        "tencent": {
            "secret_id": get_value(db, KEY_SMS_TENCENT_SECRET_ID),
            "secret_key": _decrypted(db, KEY_SMS_TENCENT_SECRET_KEY),
            "sdk_app_id": get_value(db, KEY_SMS_TENCENT_APP_ID),
            "sign_name": get_value(db, KEY_SMS_TENCENT_SIGN),
            "template_id": get_value(db, KEY_SMS_TENCENT_TEMPLATE),
        },
        "huawei": {
            "app_key": get_value(db, KEY_SMS_HUAWEI_APP_KEY),
            "app_secret": _decrypted(db, KEY_SMS_HUAWEI_APP_SECRET),
            "sender": get_value(db, KEY_SMS_HUAWEI_SENDER),
            "template_id": get_value(db, KEY_SMS_HUAWEI_TEMPLATE),
        },
        "custom_http": {
            "url": get_value(db, KEY_SMS_CUSTOM_URL),
            "param_template": get_value(db, KEY_SMS_CUSTOM_TEMPLATE),
            "auth_header": _decrypted(db, KEY_SMS_CUSTOM_AUTH),
        },
    }


def _debug_fallback(desc: str, payload: str) -> str:
    """通道不可用时的兜底：非生产 → 调试通道（日志留痕）；生产 → 报错。"""
    if settings.is_dev:
        logger.warning("消息通道[%s]未配置/未联调，走调试通道：%s", desc, payload)
        return "debug"
    raise BizException(R.ADAPTER_NOT_CONFIGURED, f"{desc}未配置，请联系管理员")


def send_email(db: Session, to: str, subject: str, body: str) -> str:
    """发送邮件，返回 "real" | "debug"。SMTP 已配置时真实发送，失败抛错。"""
    cfg = email_config(db)
    if not cfg["host"]:
        return _debug_fallback("邮件通道(SMTP)", f"to={to} subject={subject} body={body}")
    security = cfg["security"]
    port = cfg["port"] or (465 if security == "ssl" else 25)
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(cfg["host"], port, timeout=_HTTP_TIMEOUT_SEC)
        else:
            server = smtplib.SMTP(cfg["host"], port, timeout=_HTTP_TIMEOUT_SEC)
            if security == "starttls":
                server.starttls()
        with server:
            if cfg["username"]:
                server.login(cfg["username"], cfg["password"])
            msg = EmailMessage()
            # 发件人字段兼容三种写法：纯邮箱 / 纯显示名 / RFC标准 "Name <addr>"。
            # MAIL FROM（信封）强制使用认证账号：腾讯企业邮等要求与认证用户一致，
            # 仅靠 From 头放显示名（头与信封可不同，属标准做法）。
            sender = (cfg["sender"] or "").strip()
            disp, saddr = parseaddr(sender)
            if not saddr or "@" not in saddr:
                disp, saddr = sender, (cfg["username"] or "")
            if not saddr:
                raise BizException(R.ADAPTER_NOT_CONFIGURED, "邮件发件人/用户名均未配置")
            msg["From"] = formataddr((disp, saddr)) if disp and disp != saddr else saddr
            msg["To"] = to
            msg["Subject"] = subject
            msg.set_content(body)
            envelope_from = cfg["username"] or saddr
            server.send_message(msg, from_addr=envelope_from)
    except BizException:
        raise
    except Exception as exc:
        logger.exception("邮件发送失败 host=%s", cfg["host"])
        raise BizException(R.GENERIC_SYSTEM, f"邮件发送失败：{type(exc).__name__}") from None
    return "real"


def send_login_code_email(db: Session, to: str, code: str) -> str:
    """登录二步验证验证码邮件（模板固定，5 分钟有效）。"""
    return send_email(db, to, "登录验证码", f"您的登录验证码为 {code}，5 分钟内有效。如非本人操作请忽略。")


def _send_sms_custom_http(cfg: dict, phone: str, code: str) -> None:
    """自定义 HTTP 短信网关：JSON 模板占位替换后 POST；非 2xx 视为失败。"""
    template = cfg["param_template"] or '{"phone": "{phone}", "code": "{code}"}'
    payload = template.replace("{phone}", phone).replace("{code}", code)
    try:
        body = json.dumps(json.loads(payload)).encode("utf-8")
    except (json.JSONDecodeError, ValueError):
        raise BizException(R.GENERIC_PARAM, "自定义短信网关参数模板不是合法 JSON") from None
    req = urllib.request.Request(cfg["url"], data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if cfg["auth_header"]:
        req.add_header("Authorization", cfg["auth_header"])
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
            if resp.status >= 400:
                raise BizException(R.GENERIC_SYSTEM, f"短信网关返回 HTTP {resp.status}")
    except BizException:
        raise
    except Exception as exc:
        logger.exception("自定义短信网关发送失败 url=%s", cfg["url"])
        raise BizException(R.GENERIC_SYSTEM, f"短信发送失败：{type(exc).__name__}") from None


def send_sms(db: Session, phone: str, code: str) -> str:
    """发送短信验证码，返回 "real" | "debug"。

    custom_http 已配置 → 真实 POST；阿里云/腾讯云/华为云已选但未联调 → 非生产降级调试通道；
    未配置 → 调试通道（非生产）/ 报错（生产）。
    """
    cfg = sms_config(db)
    provider = cfg["provider"]
    if provider == "custom_http" and cfg["custom_http"]["url"]:
        _send_sms_custom_http(cfg["custom_http"], phone, code)
        return "real"
    if provider in ("aliyun", "tencent", "huawei"):
        # 厂商网关签名对接为遗留项：预设字段已落库，发送暂走调试通道
        return _debug_fallback(f"短信通道({provider})（网关未联调）", f"phone={phone} code={code}")
    return _debug_fallback("短信通道", f"phone={phone} code={code}")
