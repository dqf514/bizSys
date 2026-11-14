"""AI 统一网关：OpenAI 兼容 chat completions 封装 + 用量日志 + 功能开关 + 配额控制。

所有 AI 调用必须经 gateway_chat 进出：
- 配置读 sys_config（系统设置页"AI 设置"卡片维护连接；AI 中心"AI 设置"页维护功能开关/配额）：
  ai.enabled / ai.base_url / ai.api_key(AES-GCM) / ai.model / ai.timeout / ai.vision_model(空=复用 ai.model)
  ai.feature.{quote|contract_ocr|task_photo|report_summary|approval_assist|contract_risk|report_assist|nl_query}
  功能开关，缺省 1
  ai.quota.user_daily_calls / ai.quota.user_daily_tokens / ai.quota.global_daily_tokens  0=不限
- 每次调用落 ai_usage_log（success/error/fallback 三态，token 统计只计 success）；
- 未配置/网络失败/结构不符抛 AiUnavailable（业务方走回退）；功能停用/配额超限抛
  AiFeatureDisabled/AiQuotaExceeded（BizException，回前端明确错误码 65002/65003）。
"""

import base64
import io
import logging
import time
from datetime import date
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core import response as R
from app.core.crypto import decrypt_text
from app.core.exceptions import BizException
from app.modules.aicenter.models import AiUsageLog
from app.modules.settings.service import get_value

logger = logging.getLogger("bizsys.ai")

KEY_AI_ENABLED = "ai.enabled"
KEY_AI_BASE_URL = "ai.base_url"
KEY_AI_API_KEY = "ai.api_key"  # AES-GCM 加密落库
KEY_AI_MODEL = "ai.model"
KEY_AI_TIMEOUT = "ai.timeout"
KEY_AI_VISION_MODEL = "ai.vision_model"  # 多模态模型，空=复用 ai.model
KEY_FEATURE_PREFIX = "ai.feature."
KEY_QUOTA_USER_CALLS = "ai.quota.user_daily_calls"
KEY_QUOTA_USER_TOKENS = "ai.quota.user_daily_tokens"
KEY_QUOTA_GLOBAL_TOKENS = "ai.quota.global_daily_tokens"

DEFAULT_TIMEOUT = 30

# 全站 AI 功能清单（新功能接入时在此登记，并在前端 ai.json 配文案）
FEATURES = (
    "quote", "contract_ocr", "task_photo", "report_summary", "approval_assist", "contract_risk",
    "report_assist", "nl_query",
)

USAGE_SUCCESS = "success"
USAGE_ERROR = "error"
USAGE_FALLBACK = "fallback"


class AiUnavailable(Exception):
    """AI 不可用：未配置 / 网络失败 / 非 2xx / 响应结构不符。消息仅供日志，不直接回前端。"""


class _AiServerError(AiUnavailable):
    """可重试的服务端错误（5xx/429）。"""


class AiFeatureDisabled(BizException):
    """功能被管理员停用（65002）。"""

    def __init__(self, feature: str):
        super().__init__(R.AI_FEATURE_DISABLED)
        self.feature = feature


class AiQuotaExceeded(BizException):
    """配额超限（65003）。"""

    def __init__(self, reason: str):
        super().__init__(R.AI_QUOTA_EXCEEDED)
        self.reason = reason


def ai_config(db: Session) -> dict:
    raw_timeout = get_value(db, KEY_AI_TIMEOUT)
    try:
        timeout = int(raw_timeout) if raw_timeout else DEFAULT_TIMEOUT
    except ValueError:
        timeout = DEFAULT_TIMEOUT
    return {
        "enabled": get_value(db, KEY_AI_ENABLED) == "1",
        "base_url": get_value(db, KEY_AI_BASE_URL).strip(),
        "api_key": decrypt_text(get_value(db, KEY_AI_API_KEY)) if get_value(db, KEY_AI_API_KEY) else "",
        "model": get_value(db, KEY_AI_MODEL).strip(),
        "vision_model": get_value(db, KEY_AI_VISION_MODEL).strip(),
        "timeout": max(1, min(timeout, 300)),
    }


def ai_ready(db: Session) -> bool:
    cfg = ai_config(db)
    return cfg["enabled"] and bool(cfg["base_url"]) and bool(cfg["api_key"]) and bool(cfg["model"])


def feature_enabled(db: Session, feature: str) -> bool:
    """功能开关：缺省启用；总开关未开视为全部停用。"""
    if not ai_ready(db):
        return False
    return get_value(db, KEY_FEATURE_PREFIX + feature) != "0"


def _quota_int(db: Session, key: str) -> int:
    try:
        return max(0, int(get_value(db, key) or 0))
    except ValueError:
        return 0


def _today_usage(db: Session, user_id: int | None) -> tuple[int, int]:
    """今日（成功调用）次数与 token 合计；user_id=None 表示全局。SQL 聚合。"""
    stmt = select(
        func.count(AiUsageLog.id),
        func.coalesce(func.sum(AiUsageLog.prompt_tokens + AiUsageLog.completion_tokens), 0),
    ).where(
        AiUsageLog.deleted == 0,
        AiUsageLog.status == USAGE_SUCCESS,
        func.date(AiUsageLog.create_time) == date.today(),
    )
    if user_id is not None:
        stmt = stmt.where(AiUsageLog.user_id == user_id)
    calls, tokens = db.execute(stmt).one()
    return int(calls), int(tokens)


def check_quota(db: Session, user_id: int | None) -> None:
    """配额检查：超限抛 AiQuotaExceeded（0=不限）。token 口径=成功调用的 prompt+completion 合计。"""
    calls_limit = _quota_int(db, KEY_QUOTA_USER_CALLS)
    tokens_limit = _quota_int(db, KEY_QUOTA_USER_TOKENS)
    global_limit = _quota_int(db, KEY_QUOTA_GLOBAL_TOKENS)
    if not (calls_limit or tokens_limit or global_limit):
        return
    if calls_limit or tokens_limit:
        calls, tokens = _today_usage(db, user_id)
        if calls_limit and calls >= calls_limit:
            raise AiQuotaExceeded("user_daily_calls")
        if tokens_limit and tokens >= tokens_limit:
            raise AiQuotaExceeded("user_daily_tokens")
    if global_limit:
        _, g_tokens = _today_usage(db, None)
        if g_tokens >= global_limit:
            raise AiQuotaExceeded("global_daily_tokens")


def log_usage(
    db: Session,
    *,
    feature: str,
    status: str,
    user=None,
    model: str = "",
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    duration_ms: int = 0,
    error: str = "",
    biz_type: str = "",
    biz_id: int | None = None,
    prompt_version: str = "",
) -> None:
    """落一行用量日志（同事务；不吞业务异常）。"""
    db.add(
        AiUsageLog(
            user_id=user.id if user else None,
            user_name=(user.name or user.username) if user else "",
            feature=feature,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            duration_ms=duration_ms,
            status=status,
            error=error[:500],
            biz_type=biz_type,
            biz_id=biz_id,
            prompt_version=prompt_version,
            create_by=user.id if user else None,
        )
    )
    db.flush()


def _row_kw(*, feature: str, user, biz_type: str, biz_id: int | None, prompt_version: str) -> dict:
    return {
        "user_id": user.id if user else None,
        "user_name": (user.name or user.username) if user else "",
        "feature": feature,
        "biz_type": biz_type,
        "biz_id": biz_id,
        "prompt_version": prompt_version,
        "create_by": user.id if user else None,
    }


def _write_log(**kw) -> None:
    """网关日志走独立会话提交：业务方回退/报错回滚后用量记录仍保留（审计口径）。"""
    from app.core.db import SessionLocal

    s = SessionLocal()
    try:
        s.add(AiUsageLog(**kw))
        s.commit()
    except Exception:
        logger.exception("ai_usage_log 写入失败")
        s.rollback()
    finally:
        s.close()


@retry(
    stop=stop_after_attempt(3),  # 首次 + 重试 2 次
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException, _AiServerError)),
    reraise=True,
)
def _post_chat(url: str, api_key: str, payload: dict, timeout: int) -> dict:
    # 环回地址绕过系统代理（httpx trust_env 在 Windows 会读注册表代理，本地/内网网关会卡死）
    host = (urlparse(url).hostname or "").lower()
    trust_env = host not in ("127.0.0.1", "localhost", "::1")
    with httpx.Client(trust_env=trust_env) as client:
        resp = client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    if resp.status_code == 429 or resp.status_code >= 500:
        raise _AiServerError(f"AI 端点 {resp.status_code}")
    if resp.status_code >= 400:
        raise AiUnavailable(f"AI 端点 {resp.status_code}")
    try:
        return resp.json()
    except ValueError as exc:
        raise AiUnavailable("AI 响应不是合法 JSON") from exc


def _image_part(data: bytes, mime: str) -> dict:
    b64 = base64.b64encode(data).decode()
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def gateway_chat(
    db: Session,
    *,
    feature: str,
    messages: list[dict],
    user=None,
    biz_type: str = "",
    biz_id: int | None = None,
    prompt_version: str = "",
    max_tokens: int = 2000,
    json_mode: bool = True,
    images: list[tuple[bytes, str]] | None = None,
) -> str:
    """统一 AI 网关入口。images=[(bytes, mime)] 走多模态（vision_model，空则复用 model）。

    返回 content 文本。未配置/失败抛 AiUnavailable；功能停用/配额超限抛
    AiFeatureDisabled/AiQuotaExceeded（均已落用量日志）。
    """
    cfg = ai_config(db)
    model = cfg["model"]
    log_kw = _row_kw(feature=feature, user=user, biz_type=biz_type, biz_id=biz_id, prompt_version=prompt_version)
    if not (cfg["enabled"] and cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        _write_log(status=USAGE_FALLBACK, error="ai_not_configured", **log_kw)
        raise AiUnavailable("AI 未启用或未配置")
    if get_value(db, KEY_FEATURE_PREFIX + feature) == "0":
        _write_log(status=USAGE_FALLBACK, error="feature_disabled", model=model, **log_kw)
        raise AiFeatureDisabled(feature)
    try:
        check_quota(db, user.id if user else None)
    except AiQuotaExceeded as exc:
        _write_log(status=USAGE_FALLBACK, error=f"quota_exceeded:{exc.reason}", model=model, **log_kw)
        raise

    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    if images:
        model = cfg["vision_model"] or cfg["model"]
        # 多模态：最后一条 user 消息改造为 text+image parts
        msgs = [dict(m) for m in messages]
        last = msgs[-1]
        parts = [{"type": "text", "text": str(last.get("content") or "")}]
        parts.extend(_image_part(data, mime) for data, mime in images)
        last["content"] = parts
    else:
        msgs = messages
    payload: dict = {"model": model, "messages": msgs, "temperature": 0.3, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    t0 = time.monotonic()
    try:
        data = _post_chat(url, cfg["api_key"], payload, cfg["timeout"])
        content = data["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise AiUnavailable("AI 响应内容为空")
    except AiUnavailable as exc:
        _write_log(status=USAGE_ERROR, model=model, duration_ms=int((time.monotonic() - t0) * 1000),
                   error=str(exc), **log_kw)
        raise
    except httpx.HTTPError as exc:
        _write_log(status=USAGE_ERROR, model=model, duration_ms=int((time.monotonic() - t0) * 1000),
                   error=f"network:{type(exc).__name__}", **log_kw)
        raise AiUnavailable(f"AI 调用网络失败：{type(exc).__name__}") from exc

    usage = data.get("usage") or {}
    _write_log(
        status=USAGE_SUCCESS,
        model=model,
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        duration_ms=int((time.monotonic() - t0) * 1000),
        **log_kw,
    )
    return content


# ---------------- 文件文本提取（合同识别/报告摘要共用） ----------------

TEXT_EXTS = {"pdf", "docx", "txt"}
IMAGE_EXTS = {"jpg", "jpeg", "png"}
MAX_EXTRACT_CHARS = 8000


def extract_text(filename: str, data: bytes) -> str:
    """pdf/docx/txt → 纯文本（截断 MAX_EXTRACT_CHARS）。不支持/提取为空抛 BizException(AI_PARSE_FAILED)。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    try:
        if ext == "pdf":
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((p.extract_text() or "") for p in reader.pages[:30])
        elif ext == "docx":
            import docx

            doc = docx.Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
        elif ext == "txt":
            text = data.decode("utf-8", errors="ignore")
        else:
            raise BizException(R.AI_PARSE_FAILED, f"不支持从 {ext or '无扩展名'} 文件提取文本（限 pdf/docx/txt）")
    except BizException:
        raise
    except Exception as exc:
        raise BizException(R.AI_PARSE_FAILED, f"文件解析失败：{type(exc).__name__}") from exc
    text = text.strip()
    if not text:
        raise BizException(R.AI_PARSE_FAILED, "未能从文件中提取到文本（扫描件请改用图片上传走视觉识别）")
    return text[:MAX_EXTRACT_CHARS]
