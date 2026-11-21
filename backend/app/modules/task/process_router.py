"""任务扩展路由 /api/v1/task（B5 CSV 19–21）。

工序流转（task_process）、七维分配（task_assignment）、全过程追溯（task_trace）、
操作流程图，以及按任务类型解析默认负责人。
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.task import extension as ext
from app.modules.task import schemas as S
from app.modules.task.models import Task, TaskAssignment, TaskProcess, TaskTrace

router = APIRouter(prefix="/task", tags=["task"], route_class=EnvelopeRoute)


def _load_task(db: Session, tid: int) -> Task:
    task = db.get(Task, tid)
    if not task or task.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "任务不存在")
    return task


def _load_process(db: Session, pid: int) -> TaskProcess:
    row = db.get(TaskProcess, pid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "工序不存在")
    return row


def _load_assignment(db: Session, aid: int) -> TaskAssignment:
    row = db.get(TaskAssignment, aid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "分配记录不存在")
    return row


def _load_trace(db: Session, tid: int) -> TaskTrace:
    row = db.get(TaskTrace, tid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND, "追溯节点不存在")
    return row


# ---------------- 工序流转 ----------------


@router.get("/tasks/{tid}/processes")
def list_processes(
    tid: int,
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    task = _load_task(db, tid)
    ext.assert_task_visible(db, task, user)
    rows = ext.list_processes(db, tid)
    return {"items": [ext.process_out(r) for r in rows], "total": len(rows)}


@router.post("/tasks/{tid}/processes", status_code=201)
def create_process(
    tid: int,
    body: S.ProcessIn,
    request: Request,
    current: User = Depends(require_perm("task:process:edit")),
    db: Session = Depends(get_db),
):
    task = _load_task(db, tid)
    ext.assert_task_visible(db, task, current)
    row = ext.add_process(db, task, body, current)
    audit(
        db, user_id=current.id, module="task", action="process_create",
        biz_type="task_process", biz_id=row.id,
        detail={"taskNo": task.task_no, "process": row.process_code},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.process_out(row)


@router.put("/processes/{pid}")
def update_process(
    pid: int,
    body: S.ProcessUpdateIn,
    request: Request,
    current: User = Depends(require_perm("task:process:edit")),
    db: Session = Depends(get_db),
):
    row = _load_process(db, pid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    if row.status in ("done", "skipped"):
        raise BizException(R.TASK_PROCESS_INVALID_STATE, "已结束的工序不可修改")
    if body.seq is not None:
        row.seq = body.seq
    if body.process_code:
        row.process_code = body.process_code
    if body.process_name:
        row.process_name = body.process_name
    if body.planned_start is not None:
        row.planned_start = body.planned_start
    if body.planned_end is not None:
        row.planned_end = body.planned_end
    if body.operator_id is not None:
        row.operator_id = body.operator_id
    if body.operator_name:
        row.operator_name = body.operator_name
    if body.dept_id is not None:
        row.dept_id = body.dept_id
    if body.dept_name:
        row.dept_name = body.dept_name
    if body.remark is not None:
        row.remark = body.remark
    db.flush()
    audit(
        db, user_id=current.id, module="task", action="process_update",
        biz_type="task_process", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.process_out(row)


@router.post("/processes/{pid}/start")
def start_process(
    pid: int,
    request: Request,
    current: User = Depends(require_perm("task:process:edit")),
    db: Session = Depends(get_db),
):
    row = _load_process(db, pid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    ext.start_process(db, task, row, current)
    audit(
        db, user_id=current.id, module="task", action="process_start",
        biz_type="task_process", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.process_out(row)


@router.post("/processes/{pid}/finish")
def finish_process(
    pid: int,
    request: Request,
    current: User = Depends(require_perm("task:process:edit")),
    db: Session = Depends(get_db),
):
    row = _load_process(db, pid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    ext.finish_process(db, task, row, current)
    audit(
        db, user_id=current.id, module="task", action="process_finish",
        biz_type="task_process", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.process_out(row)


@router.post("/processes/{pid}/skip")
def skip_process(
    pid: int,
    request: Request,
    current: User = Depends(require_perm("task:process:edit")),
    db: Session = Depends(get_db),
):
    row = _load_process(db, pid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    ext.skip_process(db, task, row, current)
    audit(
        db, user_id=current.id, module="task", action="process_skip",
        biz_type="task_process", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.process_out(row)


@router.delete("/processes/{pid}")
def delete_process(
    pid: int,
    request: Request,
    current: User = Depends(require_perm("task:process:edit")),
    db: Session = Depends(get_db),
):
    row = _load_process(db, pid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    if row.status == "running":
        raise BizException(R.TASK_PROCESS_INVALID_STATE, "进行中的工序不可删除")
    row.deleted = 1
    ext.sync_current_process(db, task)
    audit(
        db, user_id=current.id, module="task", action="process_delete",
        biz_type="task_process", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return {"id": pid, "deleted": True}


# ---------------- 七维分配 ----------------


@router.get("/tasks/{tid}/assignments")
def list_assignments(
    tid: int,
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    task = _load_task(db, tid)
    ext.assert_task_visible(db, task, user)
    rows = ext.list_assignments(db, tid)
    return {"items": [ext.assignment_out(r) for r in rows], "total": len(rows)}


@router.post("/tasks/{tid}/assignments", status_code=201)
def create_assignment(
    tid: int,
    body: S.AssignmentIn,
    request: Request,
    current: User = Depends(require_perm("task:assignment:edit")),
    db: Session = Depends(get_db),
):
    task = _load_task(db, tid)
    ext.assert_task_visible(db, task, current)
    row = TaskAssignment(
        task_id=tid,
        dimension=body.dimension,
        resource_id=body.resource_id,
        resource_code=body.resource_code,
        resource_name=body.resource_name,
        qty=body.qty,
        unit=body.unit,
        status=body.status or "pending",
        assigner_id=current.id,
        assigner_name=current.name or "",
        planned_at=body.planned_at,
        remark=body.remark,
    )
    db.add(row)
    db.flush()
    audit(
        db, user_id=current.id, module="task", action="assignment_create",
        biz_type="task_assignment", biz_id=row.id,
        detail={"taskNo": task.task_no, "dimension": row.dimension},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.assignment_out(row)


@router.put("/assignments/{aid}")
def update_assignment(
    aid: int,
    body: S.AssignmentUpdateIn,
    request: Request,
    current: User = Depends(require_perm("task:assignment:edit")),
    db: Session = Depends(get_db),
):
    row = _load_assignment(db, aid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    if body.dimension:
        row.dimension = body.dimension
    if body.resource_id is not None:
        row.resource_id = body.resource_id
    if body.resource_code:
        row.resource_code = body.resource_code
    if body.resource_name:
        row.resource_name = body.resource_name
    if body.qty is not None:
        row.qty = body.qty
    if body.unit:
        row.unit = body.unit
    if body.status:
        row.status = body.status
        if body.status == "confirmed" and not row.confirmed_at:
            row.confirmed_at = datetime.now()
    if body.planned_at is not None:
        row.planned_at = body.planned_at
    if body.remark is not None:
        row.remark = body.remark
    db.flush()
    audit(
        db, user_id=current.id, module="task", action="assignment_update",
        biz_type="task_assignment", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.assignment_out(row)


@router.delete("/assignments/{aid}")
def delete_assignment(
    aid: int,
    request: Request,
    current: User = Depends(require_perm("task:assignment:edit")),
    db: Session = Depends(get_db),
):
    row = _load_assignment(db, aid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    row.deleted = 1
    audit(
        db, user_id=current.id, module="task", action="assignment_delete",
        biz_type="task_assignment", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return {"id": aid, "deleted": True}


# ---------------- 全过程追溯 ----------------


@router.get("/tasks/{tid}/traces")
def list_traces(
    tid: int,
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    task = _load_task(db, tid)
    ext.assert_task_visible(db, task, user)
    rows = ext.list_traces(db, tid)
    return {"items": [ext.trace_out(r) for r in rows], "total": len(rows)}


@router.post("/tasks/{tid}/traces", status_code=201)
def create_trace(
    tid: int,
    body: S.TraceIn,
    request: Request,
    current: User = Depends(require_perm("task:trace:edit")),
    db: Session = Depends(get_db),
):
    task = _load_task(db, tid)
    ext.assert_task_visible(db, task, current)
    row = ext.add_trace(db, task, body, current)
    audit(
        db, user_id=current.id, module="task", action="trace_create",
        biz_type="task_trace", biz_id=row.id,
        detail={"taskNo": task.task_no, "node": row.node_code},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return ext.trace_out(row)


@router.delete("/traces/{tid}")
def delete_trace(
    tid: int,
    request: Request,
    current: User = Depends(require_perm("task:trace:edit")),
    db: Session = Depends(get_db),
):
    row = _load_trace(db, tid)
    task = _load_task(db, row.task_id)
    ext.assert_task_visible(db, task, current)
    row.deleted = 1
    audit(
        db, user_id=current.id, module="task", action="trace_delete",
        biz_type="task_trace", biz_id=row.id, detail={"taskNo": task.task_no},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return {"id": tid, "deleted": True}


# ---------------- 操作流程图 / 负责人解析 ----------------


@router.get("/tasks/{tid}/operation-flow")
def operation_flow(
    tid: int,
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    """任务操作流程图：工序节点 + 全过程追溯节点。"""
    task = _load_task(db, tid)
    ext.assert_task_visible(db, task, user)
    return ext.operation_flow(db, task)


@router.get("/tasks/{tid}/owner-suggestion")
def owner_suggestion(
    tid: int,
    user: User = Depends(require_perm("task:list")),
    db: Session = Depends(get_db),
):
    """按任务类型推荐默认负责人（CSV 20：按任务类型流转至对应负责人）。"""
    task = _load_task(db, tid)
    owner_id, owner_name = ext.resolve_owner(db, task.task_type, task.dept_id)
    return {
        "taskId": task.id,
        "taskType": task.task_type,
        "roleGroup": task.role_group or ext.role_group_of(task.task_type),
        "roleGroupText": ext.GROUP_CN.get(
            task.role_group or ext.role_group_of(task.task_type),
            task.role_group or ext.role_group_of(task.task_type),
        ),
        "ownerId": owner_id,
        "ownerName": owner_name,
    }
