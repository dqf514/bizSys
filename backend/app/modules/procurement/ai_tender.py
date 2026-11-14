"""AI 招投标辅助：投标文件要点提取与符合性初筛 + 报价比对表。

- 符合性初筛（feature=tender_assist）：AI 按公告要求逐项核对各投标文本，输出
  符合/偏离/待人工确认；bidId 与 verdict 服务端白名单归一，缺失投标按全待确认补齐；
  投标文件走文本提取（pdf/docx/txt，截 4000 字），提取失败的投标 extractable=false 全项待确认。
- 报价比对（bid_compare_rows）为确定性计算，不调 AI、不受功能开关约束。
仅辅助参考：评分与定标仍由人工完成，AI 结果不落库。
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.portal import service as portal_svc
from app.modules.procurement.models import TenderBid, TenderProject

SCREEN_PROMPT_VERSION = "v1"
SCREEN_STATUSES = ("evaluating", "awarding", "awarded")
VERDICTS = ("comply", "deviate", "manual")
_MAX_BIDS = 10
_MAX_REQUIREMENTS = 10
_PROPOSAL_CHARS = 4000
_ANNOUNCEMENT_CHARS = 6000

SCREEN_SYSTEM = (
    "你是招投标评标助手。根据招标公告要求与各投标文件文本，输出严格 JSON："
    '{"requirements":["公告中的实质性要求，最多10条，每条40字内"],'
    '"bids":[{"bidId":数字,"results":[{"requirement":"对应要求原文","verdict":"comply|deviate|manual","note":"依据，40字内"}]}]}。'
    "verdict 口径：comply=符合，deviate=偏离/不满足，manual=文本不足以判断、需人工确认；"
    "bidId 必须来自给定的投标清单；每条要求对每个投标都要给出结论。只输出 JSON，不要输出其他内容。"
)


def _tender_bids(db: Session, tid: int) -> list[TenderBid]:
    return list(
        db.scalars(
            select(TenderBid)
            .where(TenderBid.tender_id == tid, TenderBid.deleted == 0)
            .order_by(TenderBid.id)
            .limit(_MAX_BIDS)
        ).all()
    )


def _extract_proposal(bid: TenderBid) -> str | None:
    """投标文件 → 文本（截断）；无附件/读取失败/提取失败返回 None。"""
    from app.services import ai as ai_svc

    if not bid.proposal_path:
        return None
    try:
        dest, _ext = portal_svc.file_bytes(bid.proposal_path)
        return ai_svc.extract_text(bid.proposal_name or dest.name, dest.read_bytes())[:_PROPOSAL_CHARS]
    except Exception:  # noqa: BLE001 —— 单个投标提取失败不阻断整体初筛
        return None


def parse_screen_output(db_bids: list[TenderBid], raw: str) -> dict:
    """AI 输出 → {requirements, bids}。bidId 白名单过滤、verdict 归一、结果对齐补齐。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请稍后再试") from exc
    requirements = [
        str(r).strip()[:80] for r in (parsed.get("requirements") or []) if str(r).strip()
    ][:_MAX_REQUIREMENTS]
    if not requirements:
        raise BizException(R.AI_PARSE_FAILED, "AI 未能从公告中提取要求，请稍后再试")

    by_bid: dict[int, dict[str, dict]] = {}
    for b in parsed.get("bids") or []:
        if not isinstance(b, dict):
            continue
        try:
            bid_id = int(b.get("bidId"))
        except (TypeError, ValueError):
            continue
        results: dict[str, dict] = {}
        for r in b.get("results") or []:
            if not isinstance(r, dict):
                continue
            req = str(r.get("requirement") or "").strip()[:80]
            if not req:
                continue
            verdict = str(r.get("verdict") or "manual").strip().lower()
            results[req] = {
                "requirement": req,
                "verdict": verdict if verdict in VERDICTS else "manual",
                "note": str(r.get("note") or "").strip()[:120],
            }
        by_bid[bid_id] = results

    bids_out = []
    for bid in db_bids:
        results_map = by_bid.get(bid.id, {})
        extractable = bool(bid.proposal_path)
        bids_out.append(
            {
                "bidId": bid.id,
                "companyName": bid.company_name,
                "extractable": extractable,
                "results": [
                    results_map.get(req) or {"requirement": req, "verdict": "manual", "note": ""}
                    for req in requirements
                ],
            }
        )
    return {"requirements": requirements, "bids": bids_out}


def ai_bid_screen(db: Session, user: User, tender: TenderProject) -> dict:
    """符合性初筛入口（procurement:tender:evaluate）。只回分析不落库。"""
    from app.services import ai as ai_svc

    if tender.status not in SCREEN_STATUSES:
        raise BizException(R.TENDER_INVALID_STATE, "仅评标中/定标中/已定标项目可做评标辅助")
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或评标辅助功能已停用")
    bids = _tender_bids(db, tender.id)
    if not bids:
        raise BizException(R.TENDER_INVALID_STATE, "该项目暂无投标记录")

    texts: dict[int, str] = {b.id: _extract_proposal(b) for b in bids}
    ctx = {
        "tender": {"tenderNo": tender.tender_no or "", "name": tender.name},
        "announcement": (tender.announcement or "")[:_ANNOUNCEMENT_CHARS],
        "bids": [
            {
                "bidId": b.id,
                "companyName": b.company_name,
                "price": float(b.price),
                "proposalText": texts[b.id] or "（投标文件无法提取文本，全部按 manual 输出）",
            }
            for b in bids
        ],
    }
    messages = [
        {"role": "system", "content": SCREEN_SYSTEM},
        {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db,
            feature="tender_assist",
            messages=messages,
            user=user,
            biz_type="tender",
            biz_id=tender.id,
            prompt_version=SCREEN_PROMPT_VERSION,
            max_tokens=4000,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    result = parse_screen_output(bids, raw)
    # 以服务端提取结果为准修正 extractable（AI 不可信）
    for item in result["bids"]:
        item["extractable"] = bool(texts.get(item["bidId"]))
    return result


def bid_compare_rows(db: Session, tender: TenderProject) -> dict:
    """报价比对表（确定性，不调 AI）：偏离度 =(报价-预算)/预算*100；按报价升序排名。"""
    bids = _tender_bids(db, tender.id)
    budget = float(tender.budget_amount) if tender.budget_amount is not None else None
    rows = []
    for b in bids:
        price = float(b.price)
        deviation = round((price - budget) / budget * 100, 1) if budget else None
        rows.append({"bidId": b.id, "companyName": b.company_name, "price": price,
                     "deviationPercent": deviation, "submitAt": str(b.submit_at or "")[:19]})
    rows.sort(key=lambda r: r["price"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {"budgetAmount": budget, "rows": rows}
