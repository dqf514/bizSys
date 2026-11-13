"""销售系统路由 /api/v1/sales：报价模板 + 报价单（AI 报价）。

权限：sales:template:list/create/edit/publish（模板，默认仅超管）
     · sales:quote:list/create/edit/submit/send/feedback/to-contract/list:export（报价单，biz_user 全套）。
"""

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.approval import service as approval_svc
from app.modules.auth.models import User
from app.modules.sales import schemas as S
from app.modules.sales import service as svc
from app.modules.sales.models import SalesQuotation
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/sales", tags=["sales"], route_class=EnvelopeRoute)

STATUS_CN = {
    "draft": "草稿",
    "approving": "审批中",
    "approved": "已通过",
    "rejected": "已驳回",
    "sent": "已发送",
    "accepted": "客户已接受",
    "declined": "客户已拒绝",
    "voided": "已作废",
}

EXPORT_COLS = [
    {"key": "quoteNo", "label": "报价编号", "width": 18},
    {"key": "title", "label": "报价标题", "width": 32},
    {"key": "customerName", "label": "客户", "width": 24},
    {"key": "contactName", "label": "联系人", "width": 12},
    {"key": "totalAmount", "label": "合计金额", "width": 14},
    {"key": "taxRate", "label": "税率%", "width": 8},
    {"key": "validUntil", "label": "有效期至", "width": 12},
    {"key": "status", "label": "状态", "width": 12},
    {"key": "sentChannel", "label": "发送通道", "width": 10},
    {"key": "sentAt", "label": "发送时间", "width": 19},
    {"key": "createTime", "label": "创建时间", "width": 19},
]


# ---------------- 报价模板 ----------------


@router.get("/templates")
def list_templates(
    _: User = Depends(require_perm("sales:template:list")),
    db: Session = Depends(get_db),
):
    """模板管理列表（全部版本）。"""
    return svc.list_templates(db)


@router.get("/templates/options")
def template_options(
    _: User = Depends(require_perm("sales:quote:create")),
    db: Session = Depends(get_db),
):
    """报价编辑页模板选择器（仅 published）；挂在报价权限上，模板管理权限默认仅超管。"""
    return svc.template_options(db)


@router.post("/templates", status_code=201)
def create_template(
    body: S.TemplateIn,
    current: User = Depends(require_perm("sales:template:create")),
    db: Session = Depends(get_db),
):
    data = svc.create_template(db, body, current)
    record(db, user_id=current.id, module="sales", action="sales_template_create", biz_type="sales_quote_template",
           biz_id=data["id"], detail={"key": body.key, "name": body.name})
    db.commit()
    return data


@router.get("/templates/{tid}")
def get_template(
    tid: int,
    _: User = Depends(require_perm("sales:template:list")),
    db: Session = Depends(get_db),
):
    return svc.get_template(db, tid)


@router.put("/templates/{tid}")
def update_template(
    tid: int,
    body: S.TemplateIn,
    current: User = Depends(require_perm("sales:template:edit")),
    db: Session = Depends(get_db),
):
    data = svc.update_template(db, tid, body, current)
    record(db, user_id=current.id, module="sales", action="sales_template_update", biz_type="sales_quote_template",
           biz_id=tid, detail={"key": body.key})
    db.commit()
    return data


@router.post("/templates/{tid}/new-version", status_code=201)
def new_version_template(
    tid: int,
    current: User = Depends(require_perm("sales:template:edit")),
    db: Session = Depends(get_db),
):
    data = svc.new_version_template(db, tid, current)
    record(db, user_id=current.id, module="sales", action="sales_template_new_version",
           biz_type="sales_quote_template", biz_id=data["id"], detail={"tplVersion": data["tplVersion"]})
    db.commit()
    return data


@router.post("/templates/{tid}/publish")
def publish_template(
    tid: int,
    current: User = Depends(require_perm("sales:template:publish")),
    db: Session = Depends(get_db),
):
    data = svc.publish_template(db, tid, current)
    record(db, user_id=current.id, module="sales", action="sales_template_publish",
           biz_type="sales_quote_template", biz_id=tid)
    db.commit()
    return data


@router.post("/templates/{tid}/disable")
def disable_template(
    tid: int,
    current: User = Depends(require_perm("sales:template:publish")),
    db: Session = Depends(get_db),
):
    data = svc.disable_template(db, tid, current)
    record(db, user_id=current.id, module="sales", action="sales_template_disable",
           biz_type="sales_quote_template", biz_id=tid)
    db.commit()
    return data


@router.delete("/templates/{tid}")
def delete_template(
    tid: int,
    current: User = Depends(require_perm("sales:template:edit")),
    db: Session = Depends(get_db),
):
    svc.delete_template(db, tid)
    record(db, user_id=current.id, module="sales", action="sales_template_delete",
           biz_type="sales_quote_template", biz_id=tid)
    db.commit()
    return None


# ---------------- 报价单 ----------------
# 注意：counts/export/options/ai-generate 等静态段必须放在 /quotations/{qid} 之前，避免被路径参数抢占


@router.get("/quotations")
def list_quotations(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    _: User = Depends(require_perm("sales:quote:list")),
    db: Session = Depends(get_db),
):
    return svc.list_quotations(db, PageParams(page=page, size=size), request.query_params)


@router.get("/quotations/counts")
def quotation_counts(
    _: User = Depends(require_perm("sales:quote:list")),
    db: Session = Depends(get_db),
):
    return svc.counts(db)


@router.get("/quotations/export")
def export_quotations(
    request: Request,
    current: User = Depends(require_perm("sales:quote:list:export")),
    db: Session = Depends(get_db),
):
    rows = []
    total = None
    page = 1
    while total is None or len(rows) < total:
        data = svc.list_quotations(db, PageParams(page=page, size=200), request.query_params)
        total = data["total"]
        for item in data["items"]:
            item = dict(item)
            item["status"] = STATUS_CN.get(item["status"], item["status"])
            rows.append(item)
        if not data["items"] or page > 500:  # 防呆上限 10 万行
            break
        page += 1
    payload = export_xlsx_styled(rows, EXPORT_COLS, "sales_quotations")
    record(db, user_id=current.id, module="sales", action="sales_quote_export", detail={"count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('sales_quotations')}"},
    )


@router.post("/quotations/ai-generate")
def ai_generate(
    body: S.AiGenerateIn,
    current: User = Depends(require_perm("sales:quote:create")),
    db: Session = Depends(get_db),
):
    """AI 生成报价草稿：结果仅回填前端不落库；source=ai/template/history，回退原因记审计。"""
    data = svc.ai_generate(db, current, body)
    record(db, user_id=current.id, module="sales", action="sales_quote_ai_generate",
           biz_type="sales_quotation", biz_id=body.quotation_id or 0,
           detail={"source": data["source"], "fallbackReason": data.get("fallbackReason") or ""})
    db.commit()
    return data


@router.post("/quotations", status_code=201)
def create_quotation(
    body: S.QuotationIn,
    current: User = Depends(require_perm("sales:quote:create")),
    db: Session = Depends(get_db),
):
    q = svc.create_quotation(db, current, body)
    record(db, user_id=current.id, module="sales", action="sales_quote_create", biz_type="sales_quotation",
           biz_id=q.id, detail={"title": q.title, "customerId": q.customer_id})
    db.commit()
    return svc._out(q, with_items=True)


@router.get("/quotations/{qid}")
def get_quotation(
    qid: int,
    _: User = Depends(require_perm("sales:quote:list")),
    db: Session = Depends(get_db),
):
    q = svc._load(db, qid)
    data = svc._out(q, with_items=True)
    data["timeline"] = approval_svc.timeline(db, "sales_quotation", qid)["records"]
    data["sendLogs"] = svc.send_logs(db, qid)
    return data


@router.put("/quotations/{qid}")
def update_quotation(
    qid: int,
    body: S.QuotationIn,
    current: User = Depends(require_perm("sales:quote:edit")),
    db: Session = Depends(get_db),
):
    q = svc.update_quotation(db, current, qid, body)
    record(db, user_id=current.id, module="sales", action="sales_quote_update", biz_type="sales_quotation",
           biz_id=qid, detail={"title": q.title})
    db.commit()
    return svc._out(q, with_items=True)


@router.delete("/quotations/{qid}")
def delete_quotation(
    qid: int,
    current: User = Depends(require_perm("sales:quote:edit")),
    db: Session = Depends(get_db),
):
    svc.delete_quotation(db, current, qid)
    record(db, user_id=current.id, module="sales", action="sales_quote_delete", biz_type="sales_quotation", biz_id=qid)
    db.commit()
    return None


@router.post("/quotations/{qid}/submit")
def submit_quotation(
    qid: int,
    body: S.SubmitIn | None = None,
    current: User = Depends(require_perm("sales:quote:submit")),
    db: Session = Depends(get_db),
):
    row = db.get(SalesQuotation, qid, with_for_update=True)  # 锁报价单行：并发提交审批只放行一个
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    q = svc.submit_quotation(db, current, qid)
    record(db, user_id=current.id, module="sales", action="sales_quote_submit", biz_type="sales_quotation",
           biz_id=qid, detail={"instanceId": q.flow_instance_id, "comment": body.comment if body else ""})
    db.commit()
    return svc._out(q, with_items=True)


@router.post("/quotations/{qid}/send")
def send_quotation(
    qid: int,
    body: S.SendIn,
    current: User = Depends(require_perm("sales:quote:send")),
    db: Session = Depends(get_db),
):
    data = svc.send_quotation(db, current, qid, body)
    record(db, user_id=current.id, module="sales", action="sales_quote_send", biz_type="sales_quotation",
           biz_id=qid, detail={"channel": body.channel, "recipient": data["sentTo"]})
    db.commit()
    return data


@router.post("/quotations/{qid}/feedback")
def feedback_quotation(
    qid: int,
    body: S.FeedbackIn,
    current: User = Depends(require_perm("sales:quote:feedback")),
    db: Session = Depends(get_db),
):
    q = svc.feedback_quotation(db, current, qid, body)
    record(db, user_id=current.id, module="sales", action="sales_quote_feedback", biz_type="sales_quotation",
           biz_id=qid, detail={"action": body.action})
    db.commit()
    return svc._out(q, with_items=True)


@router.post("/quotations/{qid}/to-contract")
def to_contract(
    qid: int,
    current: User = Depends(require_perm("sales:quote:to-contract")),
    db: Session = Depends(get_db),
):
    data = svc.to_contract(db, current, qid)
    record(db, user_id=current.id, module="sales", action="sales_quote_to_contract", biz_type="sales_quotation",
           biz_id=qid, detail=data)
    db.commit()
    return data
