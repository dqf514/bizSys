"""采购价格参考：同品名历史采购价格聚合（纯计算）+ AI 偏离点评（feature=price_ref，可关）。"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.procurement.models import PurchaseRequest, PurchaseRequestItem, StockOrder, StockOrderItem
from app.services import ai as ai_svc

PRICE_REF_PROMPT_VERSION = "v1"
PRICE_REF_SYSTEM = (
    "你是采购价格分析助手。根据同品名历史采购价格统计（JSON：次数/均价/最低/最高/最近价）"
    "与本次预估单价，给出一句简短点评（80字内）：偏离程度、是否合理、议价建议。"
    '输出严格 JSON：{"comment":"..."}。只输出 JSON。无历史数据时 comment 给"暂无历史价格可参考"。'
)

MAX_SAMPLES = 200


def _collect_prices(db: Session, item_name: str) -> list[dict]:
    """同品名历史价格：采购申请明细（预估单价）+ 已确认入库单明细（成交单价）。"""
    like = f"%{item_name.strip()}%"
    rows: list[dict] = []
    req_rows = db.execute(
        select(PurchaseRequestItem.estimate_price, PurchaseRequest.create_time)
        .join(PurchaseRequest, PurchaseRequest.id == PurchaseRequestItem.request_id)
        .where(
            PurchaseRequestItem.deleted == 0,
            PurchaseRequest.deleted == 0,
            PurchaseRequestItem.estimate_price.is_not(None),
            PurchaseRequestItem.item_name.like(like),
        )
        .order_by(PurchaseRequest.create_time.desc())
        .limit(MAX_SAMPLES)
    ).all()
    rows += [{"price": float(p), "at": str(t)[:10], "source": "request"} for p, t in req_rows]
    stock_rows = db.execute(
        select(StockOrderItem.price, StockOrder.create_time)
        .join(StockOrder, StockOrder.id == StockOrderItem.order_id)
        .where(
            StockOrderItem.deleted == 0,
            StockOrder.deleted == 0,
            StockOrder.status == "confirmed",
            StockOrderItem.price.is_not(None),
            StockOrderItem.item_name.like(like),
        )
        .order_by(StockOrder.create_time.desc())
        .limit(MAX_SAMPLES)
    ).all()
    rows += [{"price": float(p), "at": str(t)[:10], "source": "stock"} for p, t in stock_rows]
    rows.sort(key=lambda r: r["at"], reverse=True)
    return rows


def price_reference(db: Session, user: User, item_name: str, price: float | None) -> dict:
    """聚合统计 + 偏离度（确定性）；AI 点评仅在功能开启时附加，失败不影响统计。"""
    item_name = item_name.strip()
    if not item_name:
        raise BizException(R.GENERIC_PARAM, "请先填写物资名称")
    rows = _collect_prices(db, item_name)
    stats: dict = {"count": 0, "avg": None, "min": None, "max": None, "latestPrice": None, "latestAt": ""}
    if rows:
        prices = [r["price"] for r in rows]
        stats = {
            "count": len(prices),
            "avg": round(sum(prices) / len(prices), 2),
            "min": round(min(prices), 2),
            "max": round(max(prices), 2),
            "latestPrice": round(rows[0]["price"], 2),
            "latestAt": rows[0]["at"],
        }
    deviation = None
    if price is not None and stats["avg"]:
        deviation = round((price - stats["avg"]) / stats["avg"] * 100, 1)

    comment = ""
    if ai_svc.feature_enabled(db, "price_ref"):
        messages = [
            {"role": "system", "content": PRICE_REF_SYSTEM},
            {"role": "user", "content": json.dumps(
                {"itemName": item_name, "currentPrice": price, "stats": stats, "deviationPercent": deviation},
                ensure_ascii=False,
            )},
        ]
        try:
            raw = ai_svc.gateway_chat(
                db, feature="price_ref", messages=messages, user=user,
                biz_type="purchase_request", prompt_version=PRICE_REF_PROMPT_VERSION,
                json_mode=True, max_tokens=300,
            )
            parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
            comment = str(parsed.get("comment") or "").strip()[:500]
        except (ai_svc.AiUnavailable, ValueError):
            comment = ""  # AI 失败不阻断统计展示
    return {"itemName": item_name, "stats": stats, "deviationPercent": deviation, "comment": comment}
