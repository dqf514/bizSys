"""招投标内部路由 /api/v1/procurement/tenders + 合作方账号审核 /procurement/partners。"""

from datetime import datetime
from types import SimpleNamespace
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.core.security import hash_password
from app.modules.approval import service as approval_svc
from app.modules.auth.models import User
from app.modules.portal import service as portal_svc
from app.modules.portal.models import PartnerUser
from app.modules.portal.schemas import (
    PartnerCreateIn,
    PartnerPasswordResetIn,
    PartnerReviewIn,
    PartnerUpdateIn,
)
from app.modules.procurement import schemas as S
from app.modules.procurement import service as svc
from app.modules.procurement.models import (
    PurchaseContract,
    TenderBid,
    TenderEval,
    TenderProject,
    TenderRegistration,
)
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/procurement", tags=["procurement-tender"], route_class=EnvelopeRoute)

TENDER_STATUS_CN = {
    "draft": "草稿",
    "published": "已发布",
    "evaluating": "评标中",
    "awarding": "定标审批中",
    "awarded": "已定标",
    "terminated": "已终止",
}
REG_STATUS_CN = {"pending": "待审核", "approved": "已通过", "rejected": "已拒绝"}
PARTNER_STATUS_CN = {"pending": "待审核", "enabled": "已启用", "rejected": "已拒绝", "disabled": "已停用"}
TENDER_METHOD_CN = {"public": "公开招标", "invite": "邀请招标"}

TENDER_EXPORT_COLS = [
    {"key": "tenderNo", "label": "招标编号", "width": 18},
    {"key": "name", "label": "项目名称", "width": 32},
    {"key": "tenderMethod", "label": "采购方式", "width": 10},
    {"key": "budgetAmount", "label": "预算金额(元)", "width": 14},
    {"key": "bidDeadline", "label": "投标截止", "width": 19},
    {"key": "winnerName", "label": "中标单位", "width": 24},
    {"key": "winnerAmount", "label": "中标价(元)", "width": 14},
    {"key": "status", "label": "状态", "width": 12},
    {"key": "createTime", "label": "创建时间", "width": 19},
]


def _t(v) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime) else (v or "")


def _dt(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", ""))
    except ValueError:
        raise BizException(R.GENERIC_PARAM, f"时间格式不正确：{v}") from None


def _check_version(obj, version: int | None) -> None:
    if version is not None and version != obj.version:
        raise BizException(R.GENERIC_OPTIMISTIC_LOCK)


def _tender_out(t: TenderProject) -> dict:
    return {
        "id": t.id,
        "tenderNo": t.tender_no or "",
        "name": t.name,
        "requestId": t.request_id,
        "requestNo": t.request_no,
        "tenderMethod": t.tender_method,
        "budgetAmount": float(t.budget_amount) if t.budget_amount is not None else None,
        "regDeadline": _t(t.reg_deadline),
        "bidDeadline": _t(t.bid_deadline),
        "openTime": _t(t.open_time),
        "announcement": t.announcement or "",
        "status": t.status,
        "statusText": TENDER_STATUS_CN.get(t.status, t.status),
        "awardBidId": t.award_bid_id,
        "winnerBidId": t.winner_bid_id,
        "winnerName": t.winner_name,
        "winnerAmount": float(t.winner_amount) if t.winner_amount is not None else None,
        "contractId": t.contract_id,
        "flowInstanceId": t.flow_instance_id,
        "version": t.version,
        "createTime": _t(t.create_time),
        "updateTime": _t(t.update_time),
    }


def _reg_out(r: TenderRegistration) -> dict:
    return {
        "id": r.id,
        "partnerUserId": r.partner_user_id,
        "companyName": r.company_name,
        "contactName": r.contact_name,
        "contactPhone": r.contact_phone,
        "qualificationName": r.qualification_name,
        "hasAttachment": bool(r.qualification_path),
        "status": r.status,
        "statusText": REG_STATUS_CN.get(r.status, r.status),
        "reviewName": r.review_name,
        "reviewAt": _t(r.review_at),
        "reviewComment": r.review_comment,
        "createTime": _t(r.create_time),
    }


def _eval_out(e: TenderEval) -> dict:
    return {
        "id": e.id,
        "bidId": e.bid_id,
        "evaluatorId": e.evaluator_id,
        "evaluatorName": e.evaluator_name,
        "score": float(e.score),
        "comment": e.comment,
        "recommend": bool(e.recommend),
        "createTime": _t(e.create_time),
    }


def _bid_out(b: TenderBid, evals: list[TenderEval], winner_bid_id: int | None) -> dict:
    mine = [e for e in evals if e.bid_id == b.id]
    return {
        "id": b.id,
        "partnerUserId": b.partner_user_id,
        "registrationId": b.registration_id,
        "companyName": b.company_name,
        "price": float(b.price),
        "comment": b.comment or "",
        "proposalName": b.proposal_name,
        "hasProposal": bool(b.proposal_path),
        "submitAt": _t(b.submit_at),
        "isWinner": winner_bid_id == b.id,
        "evals": [_eval_out(e) for e in mine],
        "avgScore": round(sum(float(e.score) for e in mine) / len(mine), 1) if mine else None,
    }


def _get_tender(db: Session, tid: int, lock: bool = False) -> TenderProject:
    t = db.get(TenderProject, tid, with_for_update=lock)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return t


def _apply(t: TenderProject, body: S.TenderProjectIn, db: Session) -> None:
    t.name = body.name
    if body.request_id:
        from app.modules.procurement.models import PurchaseRequest

        r = db.get(PurchaseRequest, body.request_id)
        if not r or r.deleted:
            raise BizException(R.GENERIC_NOT_FOUND, "关联采购申请不存在")
        t.request_id = r.id
        t.request_no = r.request_no or ""
    else:
        t.request_id = None
        t.request_no = ""
    t.tender_method = body.tender_method
    t.budget_amount = body.budget_amount
    t.reg_deadline = _dt(body.reg_deadline)
    t.bid_deadline = _dt(body.bid_deadline)
    t.open_time = _dt(body.open_time)
    t.announcement = body.announcement


def _tender_filtered(db: Session, request: Request, page: PageParams):
    stmt = select(TenderProject)
    return apply_list_filters(
        stmt,
        TenderProject,
        request.query_params,
        db,
        page,
        search_cols=["name", "tender_no", "request_no"],
        filter_cols={"status", "tender_method"},
        range_cols={"bid_deadline", "create_time"},
        sort_cols={"update_time", "create_time", "id", "tender_no", "name", "budget_amount", "bid_deadline", "status"},
    )


@router.get("/tenders")
def list_tenders(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("procurement:tender:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _tender_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_tender_out(t) for t in rows], "total": total, "page": page, "size": size}


@router.get("/tenders/counts")
def tender_counts(user: User = Depends(require_perm("procurement:tender:list")), db: Session = Depends(get_db)):
    rows = db.execute(
        select(TenderProject.status, func.count()).where(TenderProject.deleted == 0).group_by(TenderProject.status)
    ).all()
    data = {s: 0 for s in TENDER_STATUS_CN}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.get("/tenders/{tid}")
def get_tender(tid: int, user: User = Depends(require_perm("procurement:tender:list")), db: Session = Depends(get_db)):
    t = _get_tender(db, tid)
    data = _tender_out(t)
    regs = db.scalars(
        select(TenderRegistration)
        .where(TenderRegistration.tender_id == tid, TenderRegistration.deleted == 0)
        .order_by(TenderRegistration.id)
    ).all()
    data["registrations"] = [_reg_out(r) for r in regs]
    bids = db.scalars(
        select(TenderBid).where(TenderBid.tender_id == tid, TenderBid.deleted == 0).order_by(TenderBid.id)
    ).all()
    evals = db.scalars(
        select(TenderEval).where(TenderEval.tender_id == tid, TenderEval.deleted == 0).order_by(TenderEval.id)
    ).all()
    data["bids"] = [_bid_out(b, list(evals), t.winner_bid_id) for b in bids]
    data["timeline"] = approval_svc.timeline(db, "tender_award", tid)["records"]
    if t.contract_id:
        c = db.get(PurchaseContract, t.contract_id)
        data["contractNo"] = (c.contract_no or "") if c else ""
        data["contractStatus"] = c.status if c else ""
    return data


@router.post("/tenders", status_code=201)
def create_tender(
    body: S.TenderProjectIn,
    current: User = Depends(require_perm("procurement:tender:create")),
    db: Session = Depends(get_db),
):
    t = TenderProject(tender_no=None, status="draft", create_by=current.id)
    _apply(t, body, db)
    db.add(t)
    db.flush()
    audit(db, user_id=current.id, module="procurement", action="tender_create", biz_type="tender", biz_id=t.id)
    db.commit()
    return _tender_out(t)


@router.put("/tenders/{tid}")
def update_tender(
    tid: int,
    body: S.TenderProjectIn,
    current: User = Depends(require_perm("procurement:tender:edit")),
    db: Session = Depends(get_db),
):
    t = _get_tender(db, tid)
    if t.status != "draft":
        raise BizException(R.TENDER_INVALID_STATE, "仅草稿可编辑")
    _check_version(t, body.version)
    _apply(t, body, db)
    t.version += 1
    t.update_by = current.id
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="procurement", action="tender_update", biz_type="tender", biz_id=tid)
    db.commit()
    return _tender_out(t)


@router.delete("/tenders/{tid}")
def delete_tender(
    tid: int,
    current: User = Depends(require_perm("procurement:tender:delete")),
    db: Session = Depends(get_db),
):
    t = _get_tender(db, tid)
    if t.status != "draft":
        raise BizException(R.TENDER_INVALID_STATE, "仅草稿可删除")
    t.deleted = 1
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="procurement", action="tender_delete", biz_type="tender", biz_id=tid)
    db.commit()
    return None


@router.post("/tenders/{tid}/publish")
def publish_tender(
    tid: int,
    current: User = Depends(require_perm("procurement:tender:publish")),
    db: Session = Depends(get_db),
):
    """发布：发 ZB 编号 + 对外可见（门户公告）。要求截止时间已配置且在未来。"""
    t = _get_tender(db, tid, lock=True)
    if t.status != "draft":
        raise BizException(R.TENDER_INVALID_STATE, "仅草稿可发布")
    if not t.reg_deadline or not t.bid_deadline:
        raise BizException(R.GENERIC_PARAM, "请先配置报名截止与投标截止时间")
    if t.reg_deadline > t.bid_deadline:
        raise BizException(R.GENERIC_PARAM, "报名截止不能晚于投标截止")
    t.tender_no = next_no(db, "tender")
    t.status = "published"
    t.version += 1
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="procurement", action="tender_publish",
          biz_type="tender", biz_id=tid, detail={"tenderNo": t.tender_no})
    db.commit()
    return _tender_out(t)


@router.post("/tenders/{tid}/terminate")
def terminate_tender(
    tid: int,
    current: User = Depends(require_perm("procurement:tender:terminate")),
    db: Session = Depends(get_db),
):
    t = _get_tender(db, tid, lock=True)
    if t.status in ("awarded", "terminated", "draft"):
        raise BizException(R.TENDER_INVALID_STATE, f"状态「{TENDER_STATUS_CN.get(t.status, t.status)}」不允许终止")
    if t.status == "awarding":
        raise BizException(R.TENDER_INVALID_STATE, "定标审批中，请先撤回审批")
    t.status = "terminated"
    t.version += 1
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="procurement", action="tender_terminate", biz_type="tender", biz_id=tid)
    db.commit()
    return _tender_out(t)


@router.post("/tenders/{tid}/start-evaluation")
def start_evaluation(
    tid: int,
    current: User = Depends(require_perm("procurement:tender:evaluate")),
    db: Session = Depends(get_db),
):
    """进入评标：投标即刻关闭（portal 侧 status!=published 拒绝报名/投标）。"""
    t = _get_tender(db, tid, lock=True)
    if t.status != "published":
        raise BizException(R.TENDER_INVALID_STATE, "仅已发布项目可进入评标")
    t.status = "evaluating"
    t.version += 1
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="procurement", action="tender_start_evaluation", biz_type="tender", biz_id=tid)
    db.commit()
    return _tender_out(t)


@router.post("/tenders/{tid}/registrations/{rid}/review")
def review_registration(
    tid: int,
    rid: int,
    body: S.RegistrationReviewIn,
    current: User = Depends(require_perm("procurement:tender:review")),
    db: Session = Depends(get_db),
):
    r = db.get(TenderRegistration, rid, with_for_update=True)
    if not r or r.deleted or r.tender_id != tid:
        raise BizException(R.GENERIC_NOT_FOUND)
    if r.status != "pending":
        raise BizException(R.TENDER_INVALID_STATE, "报名已审核")
    r.status = "approved" if body.approve else "rejected"
    r.review_by = current.id
    r.review_name = current.name or current.username
    r.review_at = datetime.now()
    r.review_comment = body.comment
    audit(db, user_id=current.id, module="procurement",
          action="tender_registration_approve" if body.approve else "tender_registration_reject",
          biz_type="tender_registration", biz_id=rid, detail={"tenderId": tid, "comment": body.comment})
    db.commit()
    return _reg_out(r)


@router.post("/tenders/{tid}/evals", status_code=201)
def upsert_eval(
    tid: int,
    body: S.TenderEvalIn,
    current: User = Depends(require_perm("procurement:tender:evaluate")),
    db: Session = Depends(get_db),
):
    """评标：一评标人对一投标一条（重复提交覆盖）；仅评标中状态。"""
    t = _get_tender(db, tid)
    if t.status != "evaluating":
        raise BizException(R.TENDER_INVALID_STATE, "仅评标中可评分")
    bid = db.get(TenderBid, body.bid_id)
    if not bid or bid.deleted or bid.tender_id != tid:
        raise BizException(R.GENERIC_NOT_FOUND, "投标不存在")
    e = db.scalar(
        select(TenderEval).where(
            TenderEval.bid_id == bid.id, TenderEval.evaluator_id == current.id, TenderEval.deleted == 0
        )
    )
    if e:
        e.score = body.score
        e.comment = body.comment
        e.recommend = 1 if body.recommend else 0
        e.update_time = datetime.now()
    else:
        e = TenderEval(
            tender_id=tid,
            bid_id=bid.id,
            evaluator_id=current.id,
            evaluator_name=current.name or current.username,
            score=body.score,
            comment=body.comment,
            recommend=1 if body.recommend else 0,
        )
        db.add(e)
    db.flush()
    audit(db, user_id=current.id, module="procurement", action="tender_eval",
          biz_type="tender", biz_id=tid, detail={"bidId": bid.id, "score": body.score, "recommend": body.recommend})
    db.commit()
    return _eval_out(e)


@router.post("/tenders/{tid}/award")
def award_tender(
    tid: int,
    body: S.TenderAwardIn,
    current: User = Depends(require_perm("procurement:tender:award")),
    db: Session = Depends(get_db),
):
    """定标：选择中标投标 → 定标审批（tender_award_approve）；通过即 awarded。"""
    t = _get_tender(db, tid, lock=True)
    if t.status != "evaluating":
        raise BizException(R.TENDER_INVALID_STATE, "仅评标中可提交定标")
    bid = db.get(TenderBid, body.bid_id)
    if not bid or bid.deleted or bid.tender_id != tid:
        raise BizException(R.GENERIC_NOT_FOUND, "投标不存在")
    inst = approval_svc.start(
        db,
        biz_type="tender_award",
        biz_id=t.id,
        definition_code="tender_award_approve",
        title=f"{t.tender_no} {t.name} 定标",
        initiator=current,
        form_snapshot=svc.tender_snapshot(t, bid),
    )
    t.status = "awarding"
    t.award_bid_id = bid.id
    t.flow_instance_id = inst.id
    t.version += 1
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="procurement", action="tender_award_submit",
          biz_type="tender", biz_id=tid, detail={"bidId": bid.id, "instanceId": inst.id})
    db.commit()
    return _tender_out(t)


@router.post("/tenders/{tid}/generate-contract", status_code=201)
def generate_contract(
    tid: int,
    current: User = Depends(require_perm("procurement:contract:create")),
    db: Session = Depends(get_db),
):
    """定标结果 → 采购合同草稿（幂等：一项目一合同）。供应商=中标账号绑定的往来单位，金额=中标价。"""
    t = _get_tender(db, tid)
    if t.status != "awarded" or not t.winner_bid_id:
        raise BizException(R.TENDER_NOT_AWARDED)
    if t.contract_id:
        c = db.get(PurchaseContract, t.contract_id)
        if c and not c.deleted:
            from app.modules.procurement.router import _contract_out

            return _contract_out(c)
    bid = db.get(TenderBid, t.winner_bid_id)
    partner = db.get(PartnerUser, bid.partner_user_id) if bid else None
    if not partner or not partner.customer_id:
        raise BizException(R.PROCUREMENT_SUPPLIER_INVALID, "中标账号未绑定往来单位，请先在合作方账号审核中绑定")
    supplier_name = svc.load_supplier_name(db, partner.customer_id)
    c = PurchaseContract(
        contract_no=None,
        name=f"{t.name}采购合同",
        request_id=t.request_id,
        request_no=t.request_no,
        supplier_id=partner.customer_id,
        supplier_name=supplier_name,
        amount=t.winner_amount,
        handler_id=current.id,
        handler_name=current.name or current.username,
        remark=f"招标项目 {t.tender_no} 定标生成",
        status="draft",
        create_by=current.id,
    )
    db.add(c)
    db.flush()
    t.contract_id = c.id
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="procurement", action="tender_generate_contract",
          biz_type="tender", biz_id=tid, detail={"contractId": c.id, "bidId": bid.id})
    db.commit()
    from app.modules.procurement.router import _contract_out

    return _contract_out(c)


@router.post("/tenders/export")
def export_tenders(
    request: Request,
    current: User = Depends(require_perm("procurement:tender:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _tender_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = []
    for t in db.scalars(stmt).all():
        item = _tender_out(t)
        item["status"] = TENDER_STATUS_CN.get(t.status, t.status)
        item["tenderMethod"] = TENDER_METHOD_CN.get(t.tender_method, t.tender_method)
        rows.append(item)
    payload = export_xlsx_styled(rows, TENDER_EXPORT_COLS, "tenders")
    audit(db, user_id=current.id, module="procurement", action="tender_export", detail={"count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('tenders')}"},
    )


# ---------------- 内部下载报名/投标附件 ----------------


def _download(rel_path: str, original_name: str) -> Response:
    dest, _ext = portal_svc.file_bytes(rel_path)
    return Response(
        dest.read_bytes(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(original_name or 'file')}"},
    )


@router.get("/tenders/registrations/{rid}/attachment")
def registration_attachment(
    rid: int, user: User = Depends(require_perm("procurement:tender:list")), db: Session = Depends(get_db)
):
    r = db.get(TenderRegistration, rid)
    if not r or r.deleted or not r.qualification_path:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _download(r.qualification_path, r.qualification_name)


@router.get("/tenders/bids/{bid}/proposal")
def bid_proposal(
    bid: int, user: User = Depends(require_perm("procurement:tender:list")), db: Session = Depends(get_db)
):
    b = db.get(TenderBid, bid)
    if not b or b.deleted or not b.proposal_path:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _download(b.proposal_path, b.proposal_name)


# ---------------- 合作方账号审核 ----------------


def _partner_out(p: PartnerUser, db: Session | None = None) -> dict:
    customer_name = ""
    if db is not None and p.customer_id:
        from app.modules.crm.models import Customer

        c = db.get(Customer, p.customer_id)
        customer_name = c.name if c else ""
    return {
        "id": p.id,
        "username": p.username,
        "companyName": p.company_name,
        "contactName": p.contact_name,
        "phone": p.phone,
        "email": p.email,
        "status": p.status,
        "statusText": PARTNER_STATUS_CN.get(p.status, p.status),
        "customerId": p.customer_id,
        "customerName": customer_name,
        "reviewName": p.review_name,
        "reviewAt": _t(p.review_at),
        "reviewComment": p.review_comment,
        "lastLoginAt": _t(p.last_login_at),
        "createTime": _t(p.create_time),
    }


@router.get("/partners")
def list_partners(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("procurement:partner:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(PartnerUser),
        PartnerUser,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["username", "company_name", "contact_name", "phone"],
        filter_cols={"status", "customer_id"},
        range_cols={"create_time"},
        sort_cols={"create_time", "id", "username", "company_name", "status"},
    )
    rows = db.scalars(stmt).all()
    return {"items": [_partner_out(p, db) for p in rows], "total": total, "page": page, "size": size}


@router.get("/partners/counts")
def partner_counts(user: User = Depends(require_perm("procurement:partner:list")), db: Session = Depends(get_db)):
    rows = db.execute(
        select(PartnerUser.status, func.count()).where(PartnerUser.deleted == 0).group_by(PartnerUser.status)
    ).all()
    data = {s: 0 for s in PARTNER_STATUS_CN}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.post("/partners/{pid}/review")
def review_partner(
    pid: int,
    body: PartnerReviewIn,
    current: User = Depends(require_perm("procurement:partner:review")),
    db: Session = Depends(get_db),
):
    """账号审核：通过（可一并绑定往来单位）/拒绝；也可用于停用（approve=false + 已启用账号）。"""
    p = db.get(PartnerUser, pid, with_for_update=True)
    if not p or p.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if body.approve:
        if p.status not in ("pending", "rejected", "disabled"):
            raise BizException(R.TENDER_INVALID_STATE, "账号已是启用状态")
        if body.customer_id:
            svc.load_supplier_name(db, body.customer_id)  # 仅允许绑定启用的供应商往来单位
            p.customer_id = body.customer_id
        p.status = "enabled"
        action = "partner_approve"
    else:
        p.status = "rejected" if p.status == "pending" else "disabled"
        action = "partner_reject" if p.status == "rejected" else "partner_disable"
    p.review_by = current.id
    p.review_name = current.name or current.username
    p.review_at = datetime.now()
    p.review_comment = body.comment
    audit(db, user_id=current.id, module="procurement", action=action,
          biz_type="partner_user", biz_id=pid,
          detail={"username": p.username, "customerId": p.customer_id, "comment": body.comment})
    db.commit()
    return _partner_out(p, db)


# ---------------- 合作方账号 CRUD（管理侧） ----------------


def _gen_password() -> str:
    """生成一次性初始密码：12 位，含大小写字母+数字（与注册/重置同策略 ≥8 位）。"""
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(c.islower() for c in pwd) and any(c.isupper() for c in pwd) and any(c.isdigit() for c in pwd):
            return pwd


@router.post("/partners", status_code=201)
def create_partner(
    body: PartnerCreateIn,
    current: User = Depends(require_perm("procurement:partner:create")),
    db: Session = Depends(get_db),
):
    """新建门户账号：管理侧直接启用（无需审核），可指定绑定往来单位。"""
    exists = db.scalar(select(PartnerUser).where(PartnerUser.username == body.username, PartnerUser.deleted == 0))
    if exists:
        raise BizException(R.PORTAL_ACCOUNT_EXISTS)
    if body.customer_id:
        svc.load_supplier_name(db, body.customer_id)
    p = PartnerUser(
        username=body.username,
        password_hash=hash_password(body.password),
        company_name=body.company_name,
        contact_name=body.contact_name,
        phone=body.phone,
        email=body.email,
        status="enabled",
        customer_id=body.customer_id,
        review_by=current.id,
        review_name=current.name or current.username,
        review_at=datetime.now(),
        review_comment="管理侧新建",
    )
    db.add(p)
    db.flush()
    audit(db, user_id=current.id, module="procurement", action="partner_create",
          biz_type="partner_user", biz_id=p.id,
          detail={"username": p.username, "companyName": p.company_name, "customerId": p.customer_id})
    db.commit()
    return _partner_out(p, db)


@router.put("/partners/{pid}")
def update_partner(
    pid: int,
    body: PartnerUpdateIn,
    current: User = Depends(require_perm("procurement:partner:edit")),
    db: Session = Depends(get_db),
):
    """编辑资料；payload 含 customer_id 时改绑（int）/解绑（null，解绑后不能参与投标/生成合同）。"""
    p = db.get(PartnerUser, pid)
    if not p or p.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    p.company_name = body.company_name
    p.contact_name = body.contact_name
    p.phone = body.phone
    p.email = body.email
    bind_change: int | None | str = "keep"
    if "customer_id" in body.model_fields_set:
        if body.customer_id:
            svc.load_supplier_name(db, body.customer_id)
            p.customer_id = body.customer_id
            bind_change = body.customer_id
        else:
            p.customer_id = None
            bind_change = None
    audit(db, user_id=current.id, module="procurement", action="partner_update",
          biz_type="partner_user", biz_id=pid,
          detail={"username": p.username, "bindChange": bind_change})
    db.commit()
    return _partner_out(p, db)


@router.post("/partners/{pid}/password")
def reset_partner_password(
    pid: int,
    body: PartnerPasswordResetIn,
    current: User = Depends(require_perm("procurement:partner:edit")),
    db: Session = Depends(get_db),
):
    """重置密码：缺省生成随机密码并仅返回一次（告知合作方后不再可见）。"""
    p = db.get(PartnerUser, pid)
    if not p or p.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    new_pwd = body.password or _gen_password()
    p.password_hash = hash_password(new_pwd)
    audit(db, user_id=current.id, module="procurement", action="partner_reset_pwd",
          biz_type="partner_user", biz_id=pid, detail={"username": p.username})
    db.commit()
    return {"id": p.id, "username": p.username, "password": new_pwd}


@router.delete("/partners/{pid}")
def delete_partner(
    pid: int,
    current: User = Depends(require_perm("procurement:partner:delete")),
    db: Session = Depends(get_db),
):
    """软删账号；已有报名/投标记录的账号禁止删除（只能停用）。登录名加后缀释放唯一索引。"""
    p = db.get(PartnerUser, pid)
    if not p or p.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    has_reg = db.scalar(
        select(func.count()).select_from(TenderRegistration).where(
            TenderRegistration.partner_user_id == pid, TenderRegistration.deleted == 0
        )
    )
    has_bid = db.scalar(
        select(func.count()).select_from(TenderBid).where(
            TenderBid.partner_user_id == pid, TenderBid.deleted == 0
        )
    )
    if has_reg or has_bid:
        raise BizException(R.PORTAL_ACCOUNT_HAS_RECORDS)
    p.deleted = 1
    p.username = f"{p.username[:50]}#del{p.id}"
    audit(db, user_id=current.id, module="procurement", action="partner_delete",
          biz_type="partner_user", biz_id=pid, detail={"username": p.username})
    db.commit()
    return None
