"""项目管理路由 /api/v1/project（B5 CSV 31）。

项目全生命周期 + 项目任务（甘特行）+ 从任务/排期自动生成甘特。
"""

from datetime import date, datetime
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
from app.modules.contract.models import Contract
from app.modules.project import schemas as S
from app.modules.project import service as svc
from app.modules.project.models import Project, ProjectTask
from app.modules.task.models import Task
from app.services.excel import export_xlsx_styled, now_filename
from app.services.numbering import next_no

router = APIRouter(prefix="/project", tags=["project"], route_class=EnvelopeRoute)

STATUS_CN = {
    "draft": "立项中",
    "planning": "策划中",
    "executing": "执行中",
    "accepting": "验收中",
    "closed": "已结项",
    "cancelled": "已取消",
}

TASK_STATUS_CN = {
    "pending": "未开始",
    "doing": "进行中",
    "done": "已完成",
    "delayed": "已延期",
}

EXPORT_COLS = [
    {"key": "projectNo", "label": "项目编号", "width": 18},
    {"key": "name", "label": "项目名称", "width": 32},
    {"key": "customerName", "label": "客户名称", "width": 22},
    {"key": "contractNo", "label": "关联合同", "width": 18},
    {"key": "managerName", "label": "项目经理", "width": 12},
    {"key": "startDate", "label": "计划开始", "width": 12},
    {"key": "endDate", "label": "计划完成", "width": 12},
    {"key": "progress", "label": "进度", "width": 8},
    {"key": "taskCount", "label": "任务数", "width": 8},
    {"key": "statusText", "label": "状态", "width": 10},
    {"key": "createTime", "label": "创建时间", "width": 19},
]


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _d(v) -> str:
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _text(mapping: dict[str, str], value: str | None) -> str:
    key = value or ""
    return mapping.get(key, key)


def _load(db: Session, pid: int) -> Project:
    p = db.get(Project, pid)
    if not p or p.deleted:
        raise BizException(R.PROJECT_NOT_FOUND)
    return p


def _load_task(db: Session, tid: int) -> ProjectTask:
    row = db.get(ProjectTask, tid)
    if not row or row.deleted:
        raise BizException(R.PROJECT_TASK_NOT_FOUND)
    return row


def _out(p: Project, task_count: int = 0) -> dict:
    return {
        "id": p.id,
        "projectNo": p.project_no,
        "name": p.name,
        "customerId": p.customer_id,
        "customerName": p.customer_name,
        "contractId": p.contract_id,
        "contractNo": p.contract_no,
        "managerId": p.manager_id,
        "managerName": p.manager_name,
        "deptId": p.dept_id,
        "deptName": p.dept_name,
        "startDate": _d(p.start_date),
        "endDate": _d(p.end_date),
        "status": p.status,
        "statusText": _text(STATUS_CN, p.status),
        "progress": p.progress,
        "budgetAmount": float(p.budget_amount or 0),
        "actualAmount": float(p.actual_amount or 0),
        "description": p.description or "",
        "remark": p.remark or "",
        "taskCount": task_count,
        "version": p.version,
        "createTime": _t(p.create_time),
        "updateTime": _t(p.update_time),
    }


# ---------------- 项目 ----------------


@router.get("/projects")
def list_projects(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("project:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(Project),
        Project,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["project_no", "name", "customer_name", "contract_no", "manager_name"],
        filter_cols={"status", "customer_id", "contract_id", "manager_id", "dept_id"},
        range_cols={"start_date", "end_date", "create_time"},
        sort_cols={"id", "project_no", "name", "start_date", "end_date", "progress", "status", "create_time"},
    )
    rows = list(db.scalars(stmt).all())
    counts = _task_counts(db, [p.id for p in rows])
    return {
        "items": [_out(p, counts.get(p.id, 0)) for p in rows],
        "total": total,
        "page": page,
        "size": size,
    }


def _task_counts(db: Session, project_ids: list[int]) -> dict[int, int]:
    if not project_ids:
        return {}
    rows = db.execute(
        select(ProjectTask.project_id, func.count())
        .where(ProjectTask.project_id.in_(project_ids), ProjectTask.deleted == 0)
        .group_by(ProjectTask.project_id)
    ).all()
    return dict(rows)


@router.get("/projects/counts")
def project_counts(
    user: User = Depends(require_perm("project:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Project.status, func.count()).where(Project.deleted == 0).group_by(Project.status)
    ).all()
    counts = {status: cnt for status, cnt in rows}
    return {
        "all": sum(counts.values()),
        "draft": counts.get("draft", 0),
        "planning": counts.get("planning", 0),
        "executing": counts.get("executing", 0),
        "accepting": counts.get("accepting", 0),
        "closed": counts.get("closed", 0),
        "cancelled": counts.get("cancelled", 0),
    }


@router.get("/projects/{pid}")
def get_project(
    pid: int,
    user: User = Depends(require_perm("project:list")),
    db: Session = Depends(get_db),
):
    p = _load(db, pid)
    data = _out(p, _task_counts(db, [pid]).get(pid, 0))
    data["gantt"] = svc.gantt_data(db, p)
    return data


@router.post("/projects", status_code=201)
def create_project(
    body: S.ProjectIn,
    request: Request,
    current: User = Depends(require_perm("project:create")),
    db: Session = Depends(get_db),
):
    project = Project(
        project_no=next_no(db, "project"),
        name=body.name,
        customer_id=body.customer_id,
        customer_name=body.customer_name,
        contract_id=body.contract_id,
        contract_no=body.contract_no,
        manager_id=body.manager_id,
        manager_name=body.manager_name,
        dept_id=body.dept_id,
        dept_name=body.dept_name,
        start_date=body.start_date,
        end_date=body.end_date,
        status=body.status or "draft",
        budget_amount=body.budget_amount,
        description=body.description,
        remark=body.remark,
    )
    db.add(project)
    db.flush()
    audit(
        db, user_id=current.id, module="project", action="project_create",
        biz_type="prj_project", biz_id=project.id, detail={"projectNo": project.project_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return _out(project)


@router.post("/projects/from-contract", status_code=201)
def create_from_contract(
    body: S.ProjectIn,
    request: Request,
    current: User = Depends(require_perm("project:create")),
    db: Session = Depends(get_db),
):
    """基于合同立项（CSV 18：基于合同拆分任务）。合同信息覆盖入参。"""
    if not body.contract_id:
        raise BizException(R.GENERIC_PARAM, "必须指定合同")
    contract = db.get(Contract, body.contract_id)
    if not contract or contract.deleted:
        raise BizException(R.CONTRACT_INVALID_STATE, "合同不存在")
    if contract.status != "approved":
        raise BizException(R.CONTRACT_INVALID_STATE, "合同未审批通过，不能立项")
    project = Project(
        project_no=next_no(db, "project"),
        name=body.name or contract.name,
        customer_id=contract.customer_id,
        customer_name=contract.customer_name,
        contract_id=contract.id,
        contract_no=contract.contract_no or "",
        manager_id=body.manager_id or contract.handler_id,
        manager_name=body.manager_name or contract.handler_name,
        dept_id=body.dept_id,
        dept_name=body.dept_name,
        start_date=body.start_date,
        end_date=body.end_date,
        status="draft",
        budget_amount=body.budget_amount or contract.amount,
        description=body.description,
        remark=body.remark,
    )
    db.add(project)
    db.flush()
    audit(
        db, user_id=current.id, module="project", action="project_from_contract",
        biz_type="prj_project", biz_id=project.id,
        detail={"projectNo": project.project_no, "contractNo": contract.contract_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return _out(project)


@router.put("/projects/{pid}")
def update_project(
    pid: int,
    body: S.ProjectIn,
    request: Request,
    current: User = Depends(require_perm("project:edit")),
    db: Session = Depends(get_db),
):
    p = _load(db, pid)
    if body.version is not None and body.version != p.version:
        raise BizException(R.GENERIC_OPTIMISTIC_LOCK)
    p.name = body.name or p.name
    p.customer_id = body.customer_id if body.customer_id is not None else p.customer_id
    p.customer_name = body.customer_name or p.customer_name
    p.contract_id = body.contract_id if body.contract_id is not None else p.contract_id
    p.contract_no = body.contract_no or p.contract_no
    p.manager_id = body.manager_id if body.manager_id is not None else p.manager_id
    p.manager_name = body.manager_name or p.manager_name
    p.dept_id = body.dept_id if body.dept_id is not None else p.dept_id
    p.dept_name = body.dept_name or p.dept_name
    p.start_date = body.start_date if body.start_date is not None else p.start_date
    p.end_date = body.end_date if body.end_date is not None else p.end_date
    if body.status:
        p.status = body.status
    if body.budget_amount is not None:
        p.budget_amount = body.budget_amount
    p.description = body.description or p.description
    p.remark = body.remark or p.remark
    db.flush()
    audit(
        db, user_id=current.id, module="project", action="project_update",
        biz_type="prj_project", biz_id=p.id, detail={"projectNo": p.project_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return _out(p, _task_counts(db, [pid]).get(pid, 0))


@router.delete("/projects/{pid}")
def delete_project(
    pid: int,
    request: Request,
    current: User = Depends(require_perm("project:delete")),
    db: Session = Depends(get_db),
):
    p = _load(db, pid)
    if p.status not in ("draft", "cancelled"):
        raise BizException(R.PROJECT_INVALID_STATE, "只有立项中的项目可以删除")
    rows = db.scalars(select(ProjectTask).where(ProjectTask.project_id == pid, ProjectTask.deleted == 0)).all()
    for row in rows:
        row.deleted = 1
    p.deleted = 1
    audit(
        db, user_id=current.id, module="project", action="project_delete",
        biz_type="prj_project", biz_id=p.id, detail={"projectNo": p.project_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return {"id": pid, "deleted": True}


# ---------------- 项目任务（甘特行）----------------


@router.get("/projects/{pid}/tasks")
def list_project_tasks(
    pid: int,
    user: User = Depends(require_perm("project:list")),
    db: Session = Depends(get_db),
):
    p = _load(db, pid)
    rows = list(
        db.scalars(
            select(ProjectTask)
            .where(ProjectTask.project_id == pid, ProjectTask.deleted == 0)
            .order_by(ProjectTask.seq, ProjectTask.id)
        ).all()
    )
    return {"items": svc.gantt_data(db, p)["items"], "total": len(rows)}


@router.post("/projects/{pid}/tasks", status_code=201)
def create_project_task(
    pid: int,
    body: S.ProjectTaskIn,
    request: Request,
    current: User = Depends(require_perm("project:edit")),
    db: Session = Depends(get_db),
):
    p = _load(db, pid)
    if body.task_id:
        task = db.get(Task, body.task_id)
        if not task or task.deleted:
            raise BizException(R.TASK_INVALID_STATE, "关联任务不存在")
    row = ProjectTask(
        project_id=pid,
        task_id=body.task_id,
        task_no=body.task_no,
        task_name=body.task_name,
        seq=body.seq,
        group_code=body.group_code,
        owner_id=body.owner_id,
        owner_name=body.owner_name,
        start_date=body.start_date,
        end_date=body.end_date,
        progress=body.progress,
        milestone=body.milestone,
        weight=body.weight,
        status=body.status,
        depends_on=body.depends_on,
        source="manual",
        remark=body.remark,
    )
    db.add(row)
    db.flush()
    svc.recompute_progress(db, p)
    audit(
        db, user_id=current.id, module="project", action="project_task_create",
        biz_type="prj_project_task", biz_id=row.id, detail={"projectNo": p.project_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return svc.gantt_data(db, p)


@router.put("/project-tasks/{tid}")
def update_project_task(
    tid: int,
    body: S.ProjectTaskIn,
    request: Request,
    current: User = Depends(require_perm("project:edit")),
    db: Session = Depends(get_db),
):
    row = _load_task(db, tid)
    p = _load(db, row.project_id)
    row.task_no = body.task_no or row.task_no
    row.task_name = body.task_name or row.task_name
    row.seq = body.seq or row.seq
    row.group_code = body.group_code or row.group_code
    row.owner_id = body.owner_id if body.owner_id is not None else row.owner_id
    row.owner_name = body.owner_name or row.owner_name
    row.start_date = body.start_date if body.start_date is not None else row.start_date
    row.end_date = body.end_date if body.end_date is not None else row.end_date
    row.progress = body.progress
    row.milestone = body.milestone
    row.weight = body.weight if body.weight else row.weight
    row.status = body.status or row.status
    row.depends_on = body.depends_on or row.depends_on
    row.remark = body.remark or row.remark
    db.flush()
    svc.recompute_progress(db, p)
    audit(
        db, user_id=current.id, module="project", action="project_task_update",
        biz_type="prj_project_task", biz_id=row.id, detail={"projectNo": p.project_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return svc.gantt_data(db, p)


@router.delete("/project-tasks/{tid}")
def delete_project_task(
    tid: int,
    request: Request,
    current: User = Depends(require_perm("project:edit")),
    db: Session = Depends(get_db),
):
    row = _load_task(db, tid)
    p = _load(db, row.project_id)
    row.deleted = 1
    db.flush()
    svc.recompute_progress(db, p)
    audit(
        db, user_id=current.id, module="project", action="project_task_delete",
        biz_type="prj_project_task", biz_id=row.id, detail={"projectNo": p.project_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return {"id": tid, "deleted": True}


@router.post("/projects/{pid}/generate-tasks")
def generate_project_tasks(
    pid: int,
    body: S.GenerateTasksIn,
    request: Request,
    current: User = Depends(require_perm("project:edit")),
    db: Session = Depends(get_db),
):
    """从任务输入与排期自动生成项目甘特（CSV 31）。"""
    p = _load(db, pid)
    stmt = select(Task).where(Task.deleted == 0)
    if body.task_ids:
        stmt = stmt.where(Task.id.in_(body.task_ids))
    elif body.project_id:
        stmt = stmt.where(Task.contract_id == p.contract_id) if p.contract_id else stmt.where(Task.id == -1)
    else:
        stmt = stmt.where(Task.contract_id == p.contract_id) if p.contract_id else stmt.where(Task.id == -1)
    tasks = list(db.scalars(stmt).all())
    created = svc.generate_tasks(db, p, tasks, body.group_code, bool(body.overwrite))
    audit(
        db, user_id=current.id, module="project", action="project_generate_gantt",
        biz_type="prj_project", biz_id=p.id,
        detail={"projectNo": p.project_no, "tasks": len(tasks), "created": len(created)},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    data = svc.gantt_data(db, p)
    data["created"] = len(created)
    return data


@router.get("/projects/{pid}/gantt")
def project_gantt(
    pid: int,
    user: User = Depends(require_perm("project:list")),
    db: Session = Depends(get_db),
):
    p = _load(db, pid)
    return svc.gantt_data(db, p)


@router.post("/projects/export")
def export_projects(
    request: Request,
    current: User = Depends(require_perm("project:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = apply_list_filters(
        select(Project),
        Project,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=["project_no", "name", "customer_name", "contract_no", "manager_name"],
        filter_cols={"status", "customer_id", "contract_id", "manager_id", "dept_id"},
        sort_cols={"id", "project_no", "name", "start_date", "end_date", "progress", "status", "create_time"},
    )
    rows = list(db.scalars(stmt).all())
    counts = _task_counts(db, [p.id for p in rows])
    items = [_out(p, counts.get(p.id, 0)) for p in rows]
    payload = export_xlsx_styled(items, EXPORT_COLS, "projects")
    audit(
        db, user_id=current.id, module="project", action="project_export",
        detail={"count": len(rows)}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{now_filename("projects", "xlsx")}"'},
    )
