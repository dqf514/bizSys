"""AI 接入：OpenAI 兼容 chat completions 最小封装（httpx + tenacity 重试）。

配置读 sys_config（系统设置页"AI 设置"卡片维护）：
- ai.enabled   0/1 总开关
- ai.base_url  OpenAI 兼容端点（如 https://api.deepseek.com/v1）
- ai.api_key   AES-GCM 加密落库，接口只回 apiKeySet 布尔
- ai.model     模型名
- ai.timeout   秒，默认 30

未启用/未配置或调用失败一律抛 AiUnavailable，由业务方走回退策略（模板默认/历史复制）。
"""

import logging

import httpx
from sqlalchemy.orm import Session
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.crypto import decrypt_text
from app.modules.settings.service import get_value

logger = logging.getLogger("bizsys.ai")

KEY_AI_ENABLED = "ai.enabled"
KEY_AI_BASE_URL = "ai.base_url"
KEY_AI_API_KEY = "ai.api_key"  # AES-GCM 加密落库
KEY_AI_MODEL = "ai.model"
KEY_AI_TIMEOUT = "ai.timeout"

DEFAULT_TIMEOUT = 30


class AiUnavailable(Exception):
    """AI 不可用：未配置 / 网络失败 / 非 2xx / 响应结构不符。消息仅供日志，不直接回前端。"""


class _AiServerError(AiUnavailable):
    """可重试的服务端错误（5xx/429）。"""


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
        "timeout": max(1, min(timeout, 300)),
    }


def ai_ready(db: Session) -> bool:
    cfg = ai_config(db)
    return cfg["enabled"] and bool(cfg["base_url"]) and bool(cfg["api_key"]) and bool(cfg["model"])


@retry(
    stop=stop_after_attempt(3),  # 首次 + 重试 2 次
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException, _AiServerError)),
    reraise=True,
)
def _post_chat(url: str, api_key: str, payload: dict, timeout: int) -> dict:
    resp = httpx.post(
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


def chat(db: Session, messages: list[dict], *, max_tokens: int = 2000, json_mode: bool = True) -> str:
    """发起一次 chat completion，返回 content 文本。未配置/失败抛 AiUnavailable。"""
    cfg = ai_config(db)
    if not (cfg["enabled"] and cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        raise AiUnavailable("AI 未启用或未配置")
    url = f"{cfg['base_url'].rstrip('/')}/chat/completions"
    payload: dict = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        data = _post_chat(url, cfg["api_key"], payload, cfg["timeout"])
    except AiUnavailable:
        raise
    except httpx.HTTPError as exc:
        raise AiUnavailable(f"AI 调用网络失败：{type(exc).__name__}") from exc
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise AiUnavailable("AI 响应结构不符") from exc
    if not isinstance(content, str) or not content.strip():
        raise AiUnavailable("AI 响应内容为空")
    return content
