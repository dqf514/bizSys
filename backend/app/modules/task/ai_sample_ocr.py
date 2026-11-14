"""样品标签拍照识别：图片 → AI 视觉提取样品字段草稿（不落库，前端人工确认后随任务保存）。"""

import json

from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.services import ai as ai_svc

SAMPLE_OCR_PROMPT_VERSION = "v1"
SAMPLE_OCR_SYSTEM = (
    "你是样品标签识别助手。识别照片中的样品标签/铭牌，抽取字段，输出严格 JSON："
    '{"name":"样品名称","model":"型号规格","vin":"VIN/车架号（无则空）",'
    '"vehicleType":"车型（无则空）","sampleDate":"日期 YYYY-MM-DD（无则空）"}。'
    "只输出 JSON，看不清的字段留空字符串，不要臆造。"
)


def ai_ocr_sample(db: Session, user: User, filename: str, data: bytes) -> dict:
    """样品标签照片 → 字段草稿。不落库。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ai_svc.IMAGE_EXTS:
        raise BizException(R.GENERIC_PARAM, f"样品标签仅支持图片格式（{'/'.join(sorted(ai_svc.IMAGE_EXTS))}）")
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置，请手工填写或联系管理员")
    messages = [
        {"role": "system", "content": SAMPLE_OCR_SYSTEM},
        {"role": "user", "content": "请识别这张样品标签照片，抽取样品字段。"},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="sample_ocr", messages=messages, user=user,
            biz_type="task_sample", prompt_version=SAMPLE_OCR_PROMPT_VERSION,
            json_mode=True, images=[(data, f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}")],
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 视觉识别失败（模型可能不支持多模态），请手工填写") from exc
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请手工填写") from exc
    return {
        "name": str(parsed.get("name") or "").strip()[:128],
        "model": str(parsed.get("model") or "").strip()[:64],
        "vin": str(parsed.get("vin") or "").strip()[:64],
        "vehicleType": str(parsed.get("vehicleType") or "").strip()[:64],
        "sampleDate": str(parsed.get("sampleDate") or "").strip()[:10],
        "source": "ai",
    }
