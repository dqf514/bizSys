"""发票识别：发票图片/PDF → AI 提取开票字段草稿 + 服务端金额复核（不落库，人工确认后才登记）。"""

import json

from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.finance.models import Invoice, Settlement
from app.services import ai as ai_svc

INVOICE_OCR_PROMPT_VERSION = "v1"
INVOICE_OCR_SYSTEM = (
    "你是发票识别助手。从发票图片或 PDF 文本中抽取字段，输出严格 JSON："
    '{"invoiceNo":"发票号码","amount":价税合计金额(数字),"taxRate":税率百分数(数字，如 13 表示 13%，无则 null),'
    '"buyer":"购买方名称","seller":"销售方名称","invoiceDate":"开票日期 YYYY-MM-DD"}。'
    "只输出 JSON，看不清的字段留空（amount 给 0，taxRate 给 null），不要臆造。"
)


def parse_invoice_ocr(raw: str) -> dict:
    """AI 输出 → 字段草稿。无法解析抛 BizException(AI_PARSE_FAILED)。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请手工填写") from exc

    def _f(key):
        v = parsed.get(key)
        if v in (None, ""):
            return None
        try:
            return round(float(v), 2)
        except (TypeError, ValueError):
            return None

    return {
        "invoiceNo": str(parsed.get("invoiceNo") or "").strip()[:64],
        "amount": _f("amount") or 0,
        "taxRate": _f("taxRate"),
        "buyer": str(parsed.get("buyer") or "").strip()[:128],
        "seller": str(parsed.get("seller") or "").strip()[:128],
        "invoiceDate": str(parsed.get("invoiceDate") or "").strip()[:10],
    }


def ai_ocr_invoice(db: Session, user: User, invoice: Invoice, filename: str, data: bytes) -> dict:
    """发票文件 → 字段草稿 + 金额复核（对照结算单金额）。不落库。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置，请手工填写或联系管理员")
    images = None
    if ext == "pdf":
        text = ai_svc.extract_text(filename, data)
        user_msg = f"发票 PDF 的文本内容如下：\n\n{text}"
    elif ext in ai_svc.IMAGE_EXTS:
        user_msg = "请识别这张发票图片，抽取发票字段。"
        images = [(data, f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}")]
    else:
        raise BizException(R.GENERIC_PARAM, f"不支持的发票文件类型：{ext or '无扩展名'}（限 pdf/jpg/jpeg/png）")
    messages = [
        {"role": "system", "content": INVOICE_OCR_SYSTEM},
        {"role": "user", "content": user_msg},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="invoice_ocr", messages=messages, user=user,
            biz_type="invoice", biz_id=invoice.id, prompt_version=INVOICE_OCR_PROMPT_VERSION,
            json_mode=True, images=images,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试或手工填写") from exc
    fields = parse_invoice_ocr(raw)

    # 金额服务端复核：对照结算单金额（开票金额口径），偏差 >0.01 提示人工核对
    s = db.get(Settlement, invoice.settlement_id)
    check = {"settlementAmount": None, "matches": None, "diff": None}
    if s is not None:
        settle_amount = float(s.amount)
        diff = round(fields["amount"] - settle_amount, 2) if fields["amount"] else None
        check = {
            "settlementAmount": settle_amount,
            "matches": (diff is not None and abs(diff) <= 0.01),
            "diff": diff,
        }
    return {"fields": fields, "amountCheck": check, "source": "ai"}
