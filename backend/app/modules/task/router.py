"""任务路由 /api/v1/task。"""

from datetime import datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
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
from app.modules.contract.models import Contract
from app.modules.task import schemas as S
from app.modules.task import service as svc
from app.modules.task.models import Task, TaskItem, TaskSample, TaskSampleFlow
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/task", tags=["task"], route_class=EnvelopeRoute)

STATUS_CN = {
    "draft": "创建待提交",
    "approving": "立项审批中",
    "rejected": "已驳回",
    "in_progress": "分配执行中",
    "finished": "已完成",
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


def _settle_map(db: Session, ids: list[int]) -> dict[int, str]:
    """task_id -> 结算单状态（财务进度徽标：invoiced=已开票 paid=已到账）。"""
    if not ids:
        return {}
    from app.modules.finance.models import Settlement

    rows = db.scalars(select(Settlement).where(Settlement.task_id.in_(ids), Settlement.deleted == 0)).all()
    return {s.task_id: s.status for s in rows}


def _out(c: Task, labels: tuple[dict, dict], counts: tuple[int, int] = (0, 0), settle_status: str = "") -> dict:
    type_labels, block_labels = labels
    return {
        "id": c.id,
        "taskNo": c.task_no or "",
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
        "settleStatus": settle_status,
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
        "sampleNo": s.sample_no or "",
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
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    labels = _labels(db)
    cnts = _counts_for(db, [r.id for r in rows])
    settles = _settle_map(db, [r.id for r in rows])
    return {
        "items": [_out(r, labels, cnts.get(r.id, (0, 0)), settles.get(r.id, "")) for r in rows],
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
    # draft 不占正式 RW 编号：提交审批时才由编号规则发放（与合同一致，F3 流程驱动）
    t = Task(task_no=None, status="draft", create_by=current.id)
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
    data = _out(t, labels, cnts.get(t.id, (0, 0)), _settle_map(db, [t.id]).get(t.id, ""))
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
    # 提交分配除主权限外还需 task:assign（种子已发该权限码）
    "submit": ("task:submit", "task:assign"),
    "finish": ("task:edit",),
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


for _a in ("submit", "finish", "stop"):
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
    if t.status not in ("draft", "in_progress"):
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
    if row.need_report and t.task_no:
        # 草稿不占报告编号：任务提交时统一发放
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
    if t.status not in ("draft", "in_progress"):
        raise BizException(R.TASK_INVALID_STATE)
    row.name = body.name
    row.std = body.std
    row.dept = body.dept
    row.inspector = body.inspector
    row.qty = body.qty
    row.settle_type = body.settle_type
    if body.need_report and not row.need_report:
        row.need_report = 1
        if not row.report_no and t.task_no:
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

SAMPLE_STATUS_CN = {"in": "在库", "out": "出库"}

SAMPLE_EXPORT_COLS = [
    {"key": "sampleNo", "label": "样品编号", "width": 22},
    {"key": "name", "label": "样品名称", "width": 24},
    {"key": "model", "label": "型号", "width": 16},
    {"key": "vin", "label": "VIN", "width": 22},
    {"key": "vehicleType", "label": "车型", "width": 12},
    {"key": "taskNo", "label": "所属任务", "width": 18},
    {"key": "taskName", "label": "任务名称", "width": 30},
    {"key": "customerName", "label": "客户", "width": 24},
    {"key": "sampleDate", "label": "送样日期", "width": 12},
    {"key": "inStockText", "label": "库存状态", "width": 10},
    {"key": "createTime", "label": "创建时间", "width": 19},
]


def _sample_row(s: TaskSample, t: Task | None) -> dict:
    return {
        **_sample_out(s),
        "taskId": s.task_id,
        "taskNo": (t.task_no or "") if t else "",
        "taskName": t.task_name if t else "",
        "customerName": t.customer_name if t else "",
        "createTime": _t(s.create_time),
    }


def _filtered_samples(db: Session, request: Request, page: PageParams):
    """跨任务样品列表：JOIN 任务取编号/名称/客户；q 覆盖样品编号/名称/VIN/任务名/客户名。"""
    stmt = (
        select(TaskSample, Task)
        .join(Task, Task.id == TaskSample.task_id)
        .where(TaskSample.deleted == 0, Task.deleted == 0)
    )
    q = (request.query_params.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                TaskSample.sample_no.like(like),
                TaskSample.name.like(like),
                TaskSample.vin.like(like),
                Task.task_name.like(like),
                Task.customer_name.like(like),
            )
        )
    stock = request.query_params.get("status")
    if stock in ("in", "out"):
        stmt = stmt.where(TaskSample.in_stock == stock)
    sort = (request.query_params.get("sort") or "").strip()
    sort_cols = {"create_time": TaskSample.create_time, "sample_date": TaskSample.sample_date, "id": TaskSample.id}
    col = TaskSample.create_time
    direction = "desc"
    if ":" in sort:
        key, _, d = sort.partition(":")
        if key in sort_cols:
            col = sort_cols[key]
            direction = "asc" if d == "asc" else "desc"
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    stmt = stmt.order_by(col.asc() if direction == "asc" else col.desc(), TaskSample.id.desc())
    stmt = stmt.offset((page.page - 1) * page.size).limit(page.size)
    return stmt, total


@router.get("/samples")
def list_samples(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("task:sample:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _filtered_samples(db, request, PageParams(page=page, size=size))
    rows = db.execute(stmt).all()
    return {
        "items": [_sample_row(s, t) for s, t in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/samples/counts")
def sample_counts(
    user: User = Depends(require_perm("task:sample:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(TaskSample.in_stock, func.count())
        .join(Task, Task.id == TaskSample.task_id)
        .where(TaskSample.deleted == 0, Task.deleted == 0)
        .group_by(TaskSample.in_stock)
    ).all()
    data = {"in": 0, "out": 0}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.post("/samples/export")
def export_samples(
    request: Request,
    current: User = Depends(require_perm("task:sample:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _filtered_samples(db, request, SimpleNamespace(page=1, size=100_000))
    rows = db.execute(stmt).all()
    payload_rows = []
    for s, t in rows:
        item = _sample_row(s, t)
        item["inStockText"] = SAMPLE_STATUS_CN.get(s.in_stock, s.in_stock)
        payload_rows.append(item)
    payload = export_xlsx_styled(payload_rows, SAMPLE_EXPORT_COLS, "samples")
    audit(
        db,
        user_id=current.id,
        module="task",
        action="sample_export",
        detail={"count": len(payload_rows)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('samples')}"},
    )


@router.post("/tasks/{tid}/samples", status_code=201)
def add_sample(
    tid: int,
    body: S.SampleIn,
    current: User = Depends(require_perm("task:edit")),
    db: Session = Depends(get_db),
):
    t = _load(db, tid)
    if t.status in ("finished", "settled", "stopped"):
        raise BizException(R.TASK_INVALID_STATE)
    row = TaskSample(
        task_id=t.id,
        # 草稿任务无编号 → 样品同步无编号，提交时统一发放
        sample_no=svc.next_sample_no(db, t) if t.task_no else None,
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
