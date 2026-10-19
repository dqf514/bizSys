"""任务路由 /api/v1/task。"""

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.task import schemas as S
from app.modules.task import service as svc
from app.modules.task.models import Task, TaskItem, TaskSample, TaskSampleFlow
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/task", tags=["task"], route_class=EnvelopeRoute)

STATUS_CN = {
    "draft": "已创建",
    "approving": "立项审批中",
    "rejected": "已驳回",
    "assigning": "分配中",
    "assigned": "已分配",
    "in_progress": "执行中",
    "finished": "已完成",
    "closed": "已结束",
    "settled": "已结算",
    "stopped": "已停止",
}
STATUSES = list(STATUS_CN)

EXPORT_COLS = [
    {"key": "taskNo", "label": "任务编号", "width": 20},
    {"key": "taskName", "label": "任务名称", "width": 36},
    {"key": "taskTypeLabel", "label": "任务类型", "width": 14},
    {"key": "contractNo", "label": "关联合同", "width": 20},
    {"key": "customerName", "label": "客户名称", "width": 26},
    {"key": "bizBlockLabel", "label": "业务板块", "width": 14},
    {"key": "deptName", "label": "实施部门", "width": 14},
    {"key": "ownerName", "label": "负责人", "width": 10},
    {"key": "receiverUnit", "label": "受检单位", "width": 24},
    {"key": "planFinishDate", "label": "计划完成", "width": 12},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "reportCount", "label": "报告数", "width": 8},
    {"key": "sampleCount", "label": "样品数", "width": 8},
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


def _labels(db: Session) -> tuple[dict, dict]:
    return svc.dict_labels(db, "task_type"), svc.dict_labels(db, "biz_block")


def _counts_for(db: Session, ids: list[int]) -> dict[int, tuple[int, int]]:
    """task_id -> (report_count, sample_count)。"""
    if not ids:
        return {}
    item_rows = db.execute(
        select(TaskItem.task_id, func.count())
        .where(TaskItem.task_id.in_(ids), TaskItem.deleted == 0, TaskItem.need_report == 1)
        .group_by(TaskItem.task_id)
    ).all()
    sample_rows = db.execute(
        select(TaskSample.task_id, func.count())
        .where(TaskSample.task_id.in_(ids), TaskSample.deleted == 0)
        .group_by(TaskSample.task_id)
    ).all()
    items = dict(item_rows)
    samples = dict(sample_rows)
    return {i: (items.get(i, 0), samples.get(i, 0)) for i in ids}


def _out(c: Task, labels: tuple[dict, dict], counts: tuple[int, int] = (0, 0)) -> dict:
    type_labels, block_labels = labels
    return {
        "id": c.id,
        "taskNo": c.task_no,
        "taskName": c.task_name,
        "taskType": c.task_type,
        "taskTypeLabel": type_labels.get(c.task_type, c.task_type),
        "contractId": c.contract_id,
        "contractNo": c.contract_no,
        "customerId": c.customer_id,
        "customerName": c.customer_name,
        "bizBlock": c.biz_block,
        "bizBlockLabel": block_labels.get(c.biz_block, c.biz_block),
        "deptId": c.dept_id,
        "deptName": c.dept_name,
        "ownerId": c.owner_id,
        "ownerName": c.owner_name,
        "content": c.content or "",
        "partySystem": c.party_system,
        "receiver": c.receiver,
        "receiverUnit": c.receiver_unit,
        "planFinishDate": _d(c.plan_finish_date),
        "status": c.status,
        "statusText": STATUS_CN.get(c.status, c.status),
        "reportCount": counts[0],
        "sampleCount": counts[1],
        "version": c.version,
        "createTime": _t(c.create_time),
        "updateTime": _t(c.update_time),
    }


def _item_out(i: TaskItem) -> dict:
    return {
        "id": i.id,
        "itemCode": i.item_code,
        "name": i.name,
        "std": i.std,
        "dept": i.dept,
        "inspector": i.inspector,
        "qty": i.qty,
        "settleType": i.settle_type,
        "needReport": bool(i.need_report),
        "reportNo": i.report_no,
        "reportStatus": i.report_status,
    }


def _sample_out(s: TaskSample) -> dict:
    return {
        "id": s.id,
        "sampleNo": s.sample_no,
        "name": s.name,
        "model": s.model,
        "vin": s.vin,
        "vehicleType": s.vehicle_type,
        "sampleDate": _d(s.sample_date),
        "inStock": s.in_stock,
    }


def _filtered(db: Session, request: Request, page: PageParams):
    stmt = select(Task)
    return apply_list_filters(
        stmt,
        Task,
        request.query_params,
        db,
        page,
        search_cols=["task_no", "task_name", "customer_name"],
        filter_cols={"status", "task_type", "biz_block", "dept_id", "owner_id", "contract_id", "customer_id"},
        range_cols={"plan_finish_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "task_no", "plan_finish_date"},
    )


@router.get("/tasks")
def list_tasks(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    labels = _labels(db)
    cnts = _counts_for(db, [r.id for r in rows])
    return {
        "items": [_out(r, labels, cnts.get(r.id, (0, 0))) for r in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/tasks/counts")
def task_counts(
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Task.status, func.count()).where(Task.deleted == 0).group_by(Task.status)
    ).all()
    data = {s: 0 for s in STATUSES}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


def _load(db: Session, tid: int) -> Task:
    t = db.get(Task, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return t


def _apply(t: Task, body: S.TaskIn) -> None:
    t.task_name = body.task_name
    t.task_type = body.task_type
    t.content = body.content
    t.receiver = body.receiver
    t.receiver_unit = body.receiver_unit
    t.biz_block = body.biz_block
    t.dept_id = body.dept_id
    t.dept_name = body.dept_name
    t.owner_id = body.owner_id
    t.owner_name = body.owner_name
    t.party_system = body.party_system
    t.plan_finish_date = body.plan_finish_date


def _bind_contract(db: Session, t: Task, contract_id: int | None) -> None:
    if not contract_id:
        t.contract_id = None
        t.contract_no = ""
        t.customer_id = None
        t.customer_name = ""
        return
    c = db.get(Contract, contract_id)
    if not c or c.deleted or c.status != "approved":
        raise BizException(R.TASK_CONTRACT_NOT_APPROVED)
    t.contract_id = c.id
    t.contract_no = c.contract_no
    t.customer_id = c.customer_id
    t.customer_name = c.customer_name


@router.post("/tasks", status_code=201)
def create_task(
    body: S.TaskIn,
    current: User = Depends(require_perm("task:create")),
    db: Session = Depends(get_db),
):
    t = Task(task_no=next_no(db, "task", category=body.task_type or None), status="draft", create_by=current.id)
    _apply(t, body)
    _bind_contract(db, t, body.contract_id)
    if not t.owner_id:
        t.owner_id = current.id
        t.owner_name = t.owner_name or current.name or current.username
    db.add(t)
    db.flush()
    svc.sync_items(db, t, body.items)
    svc.sync_samples(db, t, body.samples)
    audit(db, user_id=current.id, module="task", action="task_create", biz_type="task", biz_id=t.id)
    db.commit()
    return _detail(db, t)


def _detail(db: Session, t: Task) -> dict:
    labels = _labels(db)
    cnts = _counts_for(db, [t.id])
    data = _out(t, labels, cnts.get(t.id, (0, 0)))
    data["items"] = [_item_out(i) for i in t.items if not i.deleted]
    data["samples"] = [_sample_out(s) for s in t.samples if not s.deleted]
    flow_rows = db.execute(
        select(TaskSampleFlow, TaskSample.sample_no)
        .outerjoin(TaskSample, TaskSample.id == TaskSampleFlow.sample_id)
        .where(TaskSampleFlow.task_id == t.id, TaskSampleFlow.deleted == 0)
        .order_by(TaskSampleFlow.at.desc(), TaskSampleFlow.id.desc())
    ).all()
    data["logs"] = [
        {
            "id": f.id,
            "sampleNo": sample_no or "",
            "action": f.action,
            "operatorName": f.operator_name,
            "createTime": _t(f.at),
            "remark": f.remark or "",
        }
        for f, sample_no in flow_rows
    ]
    data["flow"] = _flow_info(db, t)
    return data


def _flow_info(db: Session, t: Task) -> dict | None:
    """任务立项流程实例（最新一个）+ 时间线；从未发起流程返回 None。"""
    from app.modules.approval import service as approval_svc
    from app.modules.approval.models import ApprovalInstance

    inst = db.scalar(
        select(ApprovalInstance)
        .where(
            ApprovalInstance.biz_type == "task",
            ApprovalInstance.biz_id == t.id,
            ApprovalInstance.deleted == 0,
        )
        .order_by(ApprovalInstance.id.desc())
        .limit(1)
    )
    if not inst:
        return None
    return {
        "instanceId": inst.id,
        "status": inst.status,
        "definitionCode": inst.definition_code,
        "timeline": approval_svc.instance_timeline(db, inst.id)["records"],
    }


@router.get("/tasks/{tid}")
def get_task(
    tid: int,
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    return _detail(db, _load(db, tid))


@router.put("/tasks/{tid}")
def update_task(
    tid: int,
    body: S.TaskIn,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    t = _load(db, tid)
    if t.status not in ("draft", "rejected"):
        raise BizException(R.TASK_INVALID_STATE, "仅草稿/已驳回任务可编辑")
    if body.version is not None and body.version != t.version:
        raise BizException(R.GENERIC_OPTIMISTIC_LOCK)
    _apply(t, body)
    _bind_contract(db, t, body.contract_id)
    t.version += 1
    t.update_time = datetime.now()
    svc.sync_items(db, t, body.items)
    svc.sync_samples(db, t, body.samples)
    audit(db, user_id=current.id, module="task", action="task_update", biz_type="task", biz_id=tid)
    db.commit()
    return _detail(db, t)


@router.delete("/tasks/{tid}")
def delete_task(
    tid: int,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    t = _load(db, tid)
    if t.status != "draft":
        raise BizException(R.TASK_INVALID_STATE, "仅草稿任务可删除")
    t.deleted = 1
    t.update_time = datetime.now()
    audit(db, user_id=current.id, module="task", action="task_delete", biz_type="task", biz_id=tid)
    db.commit()
    return None


# ---------------- 状态动作 ----------------

_ACTION_PERM = {
    # 分配类动作（提交分配/接单）除主权限外还需 task:assign（种子已发该权限码）
    "submit": ("task:submit", "task:assign"),
    "start": ("task:edit", "task:assign"),
    "finish": ("task:edit",),
    "close": ("task:edit",),
    "stop": ("task:edit",),
}


def _action_endpoint(action: str):
    perms = _ACTION_PERM[action]

    def _run(
        tid: int,
        current: User = Depends(require_perm(perms[0])),
        db: Session = Depends(get_db),
    ):
        if "super" not in current.role_codes:
            for p in perms[1:]:
                if p not in current.perm_codes:
                    raise BizException(R.AUTH_FORBIDDEN, f"缺少权限：{p}", http_status=403)
        t = _load(db, tid)
        svc.transition(db, t, action, current)
        audit(db, user_id=current.id, module="task", action=f"task_{action}", biz_type="task", biz_id=tid,
              detail={"status": t.status})
        db.commit()
        return {"id": t.id, "status": t.status, "statusText": STATUS_CN.get(t.status, t.status)}

    _run.__name__ = f"task_{action}"
    return _run


for _a in ("submit", "start", "finish", "close", "stop"):
    router.post(f"/tasks/{{tid}}/{_a}")(_action_endpoint(_a))
del _a


# ---------------- 子条目 ----------------


@router.post("/tasks/{tid}/items", status_code=201)
def add_item(
    tid: int,
    body: S.ItemIn,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    t = _load(db, tid)
    if t.status not in ("draft", "assigning", "assigned", "in_progress"):
        raise BizException(R.TASK_INVALID_STATE)
    row = TaskItem(
        task_id=t.id,
        item_code=body.item_code or f"{len(t.items) + 1:02d}",
        name=body.name,
        std=body.std,
        dept=body.dept,
        inspector=body.inspector,
        qty=body.qty,
        settle_type=body.settle_type,
        need_report=body.need_report,
    )
    if row.need_report:
        row.report_no = next_no(db, "report")
        row.report_status = "pending"
    db.add(row)
    t.update_time = datetime.now()
    db.commit()
    return _item_out(row)


@router.put("/items/{iid}")
def update_item(
    iid: int,
    body: S.ItemIn,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(TaskItem, iid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    t = _load(db, row.task_id)
    if t.status not in ("draft", "assigning", "assigned", "in_progress"):
        raise BizException(R.TASK_INVALID_STATE)
    row.name = body.name
    row.std = body.std
    row.dept = body.dept
    row.inspector = body.inspector
    row.qty = body.qty
    row.settle_type = body.settle_type
    if body.need_report and not row.need_report:
        row.need_report = 1
        if not row.report_no:
            row.report_no = next_no(db, "report")
        row.report_status = row.report_status or "pending"
    elif not body.need_report:
        row.need_report = 0
        row.report_status = ""
    if body.item_code:
        row.item_code = body.item_code
    row.update_time = datetime.now()
    db.commit()
    return _item_out(row)


@router.delete("/items/{iid}")
def delete_item(
    iid: int,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(TaskItem, iid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    t = _load(db, row.task_id)
    if t.status != "draft":
        raise BizException(R.TASK_INVALID_STATE, "仅草稿任务可删除条目")
    row.deleted = 1
    db.commit()
    return None


# ---------------- 样品 ----------------


@router.post("/tasks/{tid}/samples", status_code=201)
def add_sample(
    tid: int,
    body: S.SampleIn,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    t = _load(db, tid)
    if t.status in ("closed", "stopped", "finished"):
        raise BizException(R.TASK_INVALID_STATE)
    row = TaskSample(
        task_id=t.id,
        sample_no=svc.next_sample_no(db, t),
        name=body.name,
        model=body.model,
        vin=body.vin,
        vehicle_type=body.vehicle_type,
        sample_date=body.sample_date,
        in_stock=body.in_stock,
    )
    db.add(row)
    t.update_time = datetime.now()
    db.flush()
    db.add(
        TaskSampleFlow(
            sample_id=row.id, task_id=t.id, action="in",
            operator_id=current.id, operator_name=current.name or current.username,
            remark="初始登记",
        )
    )
    db.commit()
    return _sample_out(row)


@router.put("/samples/{sid}")
def update_sample(
    sid: int,
    body: S.SampleIn,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(TaskSample, sid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    row.name = body.name
    row.model = body.model
    row.vin = body.vin
    row.vehicle_type = body.vehicle_type
    row.sample_date = body.sample_date
    if body.in_stock != row.in_stock:
        row.in_stock = body.in_stock
        db.add(
            TaskSampleFlow(
                sample_id=row.id, task_id=row.task_id, action=body.in_stock,
                operator_id=current.id, operator_name=current.name or current.username,
                remark="编辑时调整",
            )
        )
    row.update_time = datetime.now()
    db.commit()
    return _sample_out(row)


@router.delete("/samples/{sid}")
def delete_sample(
    sid: int,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(TaskSample, sid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    row.deleted = 1
    db.commit()
    return None


def _stock(sid: int, flag: str, current: User, db: Session) -> dict:
    row = db.get(TaskSample, sid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if row.in_stock == flag:
        raise BizException(R.TASK_INVALID_STATE, "样品已在该状态")
    row.in_stock = flag
    row.update_time = datetime.now()
    db.add(
        TaskSampleFlow(
            sample_id=row.id, task_id=row.task_id, action=flag,
            operator_id=current.id, operator_name=current.name or current.username,
        )
    )
    db.commit()
    return _sample_out(row)


@router.post("/samples/{sid}/in")
def sample_in(
    sid: int,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    return _stock(sid, "in", current, db)


@router.post("/samples/{sid}/out")
def sample_out(
    sid: int,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    return _stock(sid, "out", current, db)


# ---------------- 导出 ----------------


@router.post("/tasks/export")
def export_tasks(
    request: Request,
    current: User = Depends(require_perm("task:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.scalars(stmt).all()
    labels = _labels(db)
    cnts = _counts_for(db, [r.id for r in rows])
    payload_rows = []
    for r in rows:
        item = _out(r, labels, cnts.get(r.id, (0, 0)))
        item["status"] = STATUS_CN.get(r.status, r.status)
        payload_rows.append(item)
    payload = export_xlsx_styled(payload_rows, EXPORT_COLS, "tasks")
    audit(
        db,
        user_id=current.id,
        module="task",
        action="task_export",
        detail={"count": len(payload_rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('tasks')}"},
    )
