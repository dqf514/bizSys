"""在线任务委托路由 /api/v1/task/entrusts（B2）。

覆盖：委托单列表 / 计数 / 详情 / 业务代提交 / 受理驳回 / 生成任务 / 取消 / 导出。
门户客户侧入口在 `app/modules/portal/router.py`（独立 token 体系）。
"""

from datetime import datetime
from types import SimpleNamespace

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
from app.modules.auth.models import User
from app.modules.task import entrust as entrust_svc
from app.modules.task import schemas as S
from app.modules.task.models import TaskEntrust
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/task", tags=["task"], route_class=EnvelopeRoute)

EXPORT_COLS = [
    {"key": "entrustNo", "label": "委托单号", "width": 20},
    {"key": "title", "label": "委托标题", "width": 34},
    {"key": "entrustTypeLabel", "label": "委托类型", "width": 12},
    {"key": "contractNo", "label": "关联合同", "width": 20},
    {"key": "customerName", "label": "客户名称", "width": 26},
    {"key": "applicantName", "label": "申请人", "width": 14},
    {"key": "sourceText", "label": "来源", "width": 14},
    {"key": "handlerName", "label": "受理人", "width": 12},
    {"key": "bizOwnerName", "label": "业务负责人", "width": 12},
    {"key": "planEndDate", "label": "期望完成", "width": 12},
    {"key": "statusText", "label": "状态", "width": 12},
    {"key": "taskNo", "label": "关联任务", "width": 20},
    {"key": "createTime", "label": "创建时间", "width": 19},
]


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _d(v) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _type_labels(db: Session) -> dict:
    from app.modules.task.service import dict_labels

    return dict_labels(db, "entrust_type")


def _item_out(i) -> dict:
    return {
        "id": i.id,
        "itemCode": i.item_code,
        "name": i.name,
        "std": i.std,
        "qty": i.qty,
        "needReport": bool(i.need_report),
        "reportType": i.report_type,
        "remark": i.remark or "",
    }


def _out(e: TaskEntrust, labels: dict, with_items: bool = False) -> dict:
    data = {
        "id": e.id,
        "entrustNo": e.entrust_no or "",
        "title": e.title,
        "entrustType": e.entrust_type,
        "entrustTypeLabel": labels.get(e.entrust_type, e.entrust_type),
        "contractId": e.contract_id,
        "contractNo": e.contract_no,
        "customerId": e.customer_id,
        "customerName": e.customer_name,
        "bizBlock": e.biz_block,
        "source": e.source,
        "sourceText": "客户自助" if e.source == "portal" else "业务代提交",
        "applicantType": e.applicant_type,
        "applicantId": e.applicant_id,
        "applicantName": e.applicant_name,
        "applicantPhone": e.applicant_phone,
        "requirement": e.requirement or "",
        "sampleDesc": e.sample_desc or "",
        "planStartDate": _d(e.plan_start_date),
        "planEndDate": _d(e.plan_end_date),
        "priority": e.priority,
        "amount": float(e.amount) if e.amount is not None else None,
        "status": e.status,
        "statusText": entrust_svc.STATUS_CN.get(e.status, e.status),
        "handlerId": e.handler_id,
        "handlerName": e.handler_name,
        "bizOwnerId": e.biz_owner_id,
        "bizOwnerName": e.biz_owner_name,
        "reviewBy": e.review_by,
        "reviewName": e.review_name,
        "reviewAt": _t(e.review_at),
        "reviewComment": e.review_comment or "",
        "taskId": e.task_id,
        "taskNo": e.task_no,
        "remark": e.remark or "",
        "itemCount": len([i for i in e.items if not i.deleted]),
        "version": e.version,
        "createTime": _t(e.create_time),
        "updateTime": _t(e.update_time),
    }
    if with_items:
        data["items"] = [_item_out(i) for i in e.items if not i.deleted]
    return data


def _load(db: Session, eid: int) -> TaskEntrust:
    e = db.get(TaskEntrust, eid)
    if not e or e.deleted:
        raise BizException(R.TASK_ENTRUST_NOT_FOUND)
    return e


def _filtered(db: Session, request: Request, page: PageParams):
    stmt = select(TaskEntrust)
    return apply_list_filters(
        stmt,
        TaskEntrust,
        request.query_params,
        db,
        page,
        search_cols=["entrust_no", "title", "customer_name", "contract_no", "applicant_name"],
        filter_cols={"status", "entrust_type", "source", "customer_id", "contract_id", "handler_id", "biz_owner_id"},
        range_cols={"plan_end_date", "create_time"},
        sort_cols={
            "id", "entrust_no", "title", "entrust_type", "customer_name",
            "status", "create_time", "update_time", "plan_end_date", "priority",
        },
        default_sort=("id", "desc"),
    )


@router.get("/entrusts")
def list_entrusts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("task:entrust:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    labels = _type_labels(db)
    return {
        "items": [_out(r, labels) for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/entrusts/counts")
def entrust_counts(
    user: User = Depends(require_perm("task:entrust:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(TaskEntrust.status, func.count()).where(TaskEntrust.deleted == 0).group_by(TaskEntrust.status)
    ).all()
    data = {s: 0 for s in entrust_svc.STATUSES}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/entrusts/{eid}")
def get_entrust(
    eid: int,
    user: User = Depends(require_perm("task:entrust:list")),
    db: Session = Depends(get_db),
):
    return _out(_load(db, eid), _type_labels(db), with_items=True)


@router.post("/entrusts", status_code=201)
def create_entrust(
    body: S.EntrustIn,
    current: User = Depends(require_perm("task:entrust:create")),
    db: Session = Depends(get_db),
):
    """业务经理代提交客户委托（电话/邮件委托补录）。"""
    e = entrust_svc.create_entrust(
        db,
        body,
        source="staff",
        applicant_type="internal",
        applicant_id=current.id,
        applicant_name=current.name or current.username,
        handler_id=current.id,
        handler_name=current.name or current.username,
    )
    audit(
        db, user_id=current.id, module="task", action="entrust_create",
        biz_type="entrust", biz_id=e.id, detail={"title": e.title, "source": "staff"},
    )
    db.commit()
    return _out(e, _type_labels(db), with_items=True)


@router.post("/entrusts/{eid}/review")
def review_entrust(
    eid: int,
    body: S.EntrustReviewIn,
    current: User = Depends(require_perm("task:entrust:review")),
    db: Session = Depends(get_db),
):
    """受理（accept，发号 + 抄送业务负责人）或驳回（reject）。"""
    e = _load(db, eid)
    e.review_by = current.id
    e.review_name = current.name or current.username
    e.review_at = datetime.now()
    e.review_comment = body.comment
    if body.handler_id:
        e.handler_id = body.handler_id
        e.handler_name = body.handler_name
    elif not e.handler_id:
        e.handler_id = current.id
        e.handler_name = current.name or current.username
    if body.biz_owner_id:
        e.biz_owner_id = body.biz_owner_id
        e.biz_owner_name = body.biz_owner_name

    entrust_svc.transition(db, e, body.action)
    if body.action == "accept":
        entrust_svc.notify_biz_owner(db, e, operator_id=current.id)
    audit(
        db, user_id=current.id, module="task", action=f"entrust_{body.action}",
        biz_type="entrust", biz_id=eid, detail={"status": e.status, "comment": body.comment},
    )
    db.commit()
    return _out(e, _type_labels(db), with_items=True)


@router.post("/entrusts/{eid}/dispatch")
def dispatch_entrust(
    eid: int,
    body: S.EntrustDispatchIn,
    current: User = Depends(require_perm("task:entrust:dispatch")),
    db: Session = Depends(get_db),
):
    """受理后生成任务草稿（任务编号在任务提交时发放）。"""
    e = _load(db, eid)
    task = entrust_svc.dispatch_to_task(db, e, current, body)
    entrust_svc.transition(db, e, "dispatch")
    audit(
        db, user_id=current.id, module="task", action="entrust_dispatch",
        biz_type="entrust", biz_id=eid, detail={"taskId": task.id},
    )
    db.commit()
    return {"entrust": _out(e, _type_labels(db)), "taskId": task.id, "taskName": task.task_name}


@router.post("/entrusts/{eid}/cancel")
def cancel_entrust(
    eid: int,
    current: User = Depends(require_perm("task:entrust:review")),
    db: Session = Depends(get_db),
):
    e = _load(db, eid)
    entrust_svc.transition(db, e, "cancel")
    audit(db, user_id=current.id, module="task", action="entrust_cancel", biz_type="entrust", biz_id=eid)
    db.commit()
    return _out(e, _type_labels(db))


@router.post("/entrusts/export")
def export_entrusts(
    request: Request,
    current: User = Depends(require_perm("task:entrust:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.scalars(stmt).all()
    labels = _type_labels(db)
    payload_rows = [_out(r, labels) for r in rows]
    payload = export_xlsx_styled(payload_rows, EXPORT_COLS, "entrusts")
    audit(
        db, user_id=current.id, module="task", action="entrust_export",
        detail={"count": len(payload_rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('entrusts')}"},
    )
