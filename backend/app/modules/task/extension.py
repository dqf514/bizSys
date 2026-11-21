"""任务扩展（B5 CSV 19–21）：工序流转、七维分配、全过程追溯、角色分组。

- **工序流转**（CSV 19）：油泥 / CNC / 表面处理 等加工工序，状态 pending → running → done（可 skipped）；
  同一任务同一时刻只有一个当前工序（is_current=1），任务列表可直接显示"当前处于哪道工序"。
- **七维分配**（CSV 20）：人 / 机 / 料 / 法 / 环 / 测 / 安 —— 排程域读取其中
  equipment / person / vehicle（时段独占）与 material（数量占用）维度。
- **全过程追溯**（CSV 19）：输入 → 报告输出 / 样车归还 / 模型车发运 → 验收 / 结算。
- **角色分组**（CSV 21）：任务按仿真 / 模型 / 试验 / 委外分组；用户若只被授予
  `task:group:<组>` 权限点，则只能看到并操作本组任务。
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.deps import SUPER_ROLE
from app.core.exceptions import BizException
from app.modules.admin.models import DictItem, Role, UserRole
from app.modules.auth.models import User
from app.modules.task.models import Task, TaskAssignment, TaskProcess, TaskTrace

# 任务类型 → 角色分组
TYPE_TO_GROUP = {
    "sim": "sim",
    "simulation": "sim",
    "cfd": "sim",
    "model": "model",
    "modeling": "model",
    "test": "test",
    "windtunnel": "test",
    "wind_tunnel": "test",
    "testing": "test",
    "experiment": "test",
    "outsource": "outsource",
    "outsourcing": "outsource",
}

GROUP_CN = {
    "sim": "仿真",
    "model": "模型",
    "test": "试验",
    "outsource": "委外",
}

PROCESS_STATUS_CN = {
    "pending": "待开始",
    "running": "进行中",
    "done": "已完成",
    "skipped": "已跳过",
}

ASSIGNMENT_STATUS_CN = {
    "pending": "待分配",
    "allocated": "已分配",
    "confirmed": "已确认",
    "rejected": "已驳回",
}

DIMENSION_CN = {
    "person": "人",
    "equipment": "机",
    "material": "料",
    "method": "法",
    "env": "环",
    "test": "测",
    "safety": "安",
    "vehicle": "样车",
}

TRACE_NODE_CN = {
    "input": "任务输入",
    "output_report": "报告输出",
    "vehicle_return": "样车归还",
    "model_ship": "模型车发运",
    "accept": "验收",
    "settle": "结算",
}


def _text(mapping: dict[str, str], value: str | None) -> str:
    key = value or ""
    return mapping.get(key, key)


def role_group_of(task_type: str) -> str:
    """任务类型 → 角色分组（未登记的类型按类型本身归组）。"""
    key = (task_type or "").strip().lower()
    return TYPE_TO_GROUP.get(key, key)


def resolve_owner(db: Session, task_type: str, dept_id: int | None) -> tuple[int | None, str]:
    """按任务类型解析默认负责人。

    规则存在字典 `task_owner_rule`（value=任务类型，extra=角色编码）；
    命中后在目标部门内找该角色的在职用户，找不到则放宽到全公司。
    """
    item = db.scalar(
        select(DictItem).where(
            DictItem.dict_type_code == "task_owner_rule",
            DictItem.value == (task_type or ""),
            DictItem.status == "enabled",
            DictItem.deleted == 0,
        )
    )
    if not item or not item.extra:
        return None, ""
    role_code = item.extra.strip()
    stmt = (
        select(User)
        .join(UserRole, UserRole.user_id == User.id)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            Role.code == role_code,
            Role.status == "enabled",
            Role.deleted == 0,
            User.status == "enabled",
            User.deleted == 0,
        )
        .order_by(User.id)
    )
    if dept_id:
        scoped = db.scalars(stmt.where(User.dept_id == dept_id)).first()
        if scoped:
            return scoped.id, scoped.name or ""
    fallback = db.scalars(stmt).first()
    if fallback:
        return fallback.id, fallback.name or ""
    return None, ""


def visible_role_groups(db: Session, user: User) -> list[str] | None:
    """当前用户可见的任务角色分组。

    返回 None 表示不做限制（超管 / 未被授予任何 `task:group:*` 权限点）；
    否则返回用户被授予 `task:group:<组>` 权限点对应的分组列表。
    """
    if SUPER_ROLE in (getattr(user, "role_codes", None) or []):
        return None
    perms = getattr(user, "perm_codes", None) or []
    groups = sorted({p.split(":")[-1] for p in perms if p.startswith("task:group:")})
    if not groups:
        return None
    return groups


def assert_task_visible(db: Session, task: Task, user: User) -> None:
    """详情/编辑前的分组可见性校验。"""
    groups = visible_role_groups(db, user)
    if groups is None:
        return
    if task.role_group and task.role_group not in groups:
        label = GROUP_CN.get(task.role_group, task.role_group)
        raise BizException(R.TASK_ROLE_GROUP_DENIED, f"无权访问「{label}」组任务")


# ---------------- 工序流转 ----------------


def list_processes(db: Session, task_id: int) -> list[TaskProcess]:
    return list(
        db.scalars(
            select(TaskProcess)
            .where(TaskProcess.task_id == task_id, TaskProcess.deleted == 0)
            .order_by(TaskProcess.seq, TaskProcess.id)
        ).all()
    )


def sync_current_process(db: Session, task: Task) -> None:
    """同步任务的当前工序（is_current=1 的那一道）。"""
    rows = list_processes(db, task.id)
    current = next((r for r in rows if r.status == "running"), None)
    if current is None:
        current = next((r for r in rows if r.status == "pending"), None)
    for r in rows:
        r.is_current = 1 if current is not None and r.id == current.id else 0
    task.process_stage = current.process_code if current is not None else ""
    db.flush()


def add_process(db: Session, task: Task, body, user: User) -> TaskProcess:
    rows = list_processes(db, task.id)
    seq = body.seq or (max((r.seq for r in rows), default=0) + 1)
    row = TaskProcess(
        task_id=task.id,
        seq=seq,
        process_code=body.process_code,
        process_name=body.process_name,
        status="pending",
        planned_start=body.planned_start,
        planned_end=body.planned_end,
        operator_id=body.operator_id,
        operator_name=body.operator_name,
        dept_id=body.dept_id,
        dept_name=body.dept_name,
        remark=body.remark,
    )
    db.add(row)
    db.flush()
    sync_current_process(db, task)
    return row


def start_process(db: Session, task: Task, row: TaskProcess, user: User) -> TaskProcess:
    """开始工序：同一任务同时只允许一道工序进行中。"""
    if row.status not in ("pending",):
        raise BizException(R.TASK_PROCESS_INVALID_STATE, f"工序状态「{row.status}」不允许开始")
    running = db.scalar(
        select(TaskProcess).where(
            TaskProcess.task_id == task.id,
            TaskProcess.deleted == 0,
            TaskProcess.status == "running",
            TaskProcess.id != row.id,
        )
    )
    if running:
        raise BizException(R.TASK_PROCESS_INVALID_STATE, f"工序「{running.process_name}」仍在进行中")
    row.status = "running"
    row.actual_start = datetime.now()
    row.operator_id = row.operator_id or user.id
    row.operator_name = row.operator_name or (user.name or "")
    sync_current_process(db, task)
    return row


def finish_process(db: Session, task: Task, row: TaskProcess, user: User) -> TaskProcess:
    if row.status != "running":
        raise BizException(R.TASK_PROCESS_INVALID_STATE, f"工序状态「{row.status}」不允许完成")
    row.status = "done"
    row.actual_end = datetime.now()
    row.operator_id = row.operator_id or user.id
    row.operator_name = row.operator_name or (user.name or "")
    sync_current_process(db, task)
    return row


def skip_process(db: Session, task: Task, row: TaskProcess, user: User) -> TaskProcess:
    if row.status not in ("pending",):
        raise BizException(R.TASK_PROCESS_INVALID_STATE, f"工序状态「{row.status}」不允许跳过")
    row.status = "skipped"
    row.actual_end = datetime.now()
    sync_current_process(db, task)
    return row


# ---------------- 七维分配 ----------------


def list_assignments(db: Session, task_id: int) -> list[TaskAssignment]:
    return list(
        db.scalars(
            select(TaskAssignment)
            .where(TaskAssignment.task_id == task_id, TaskAssignment.deleted == 0)
            .order_by(TaskAssignment.id)
        ).all()
    )


# ---------------- 全过程追溯 ----------------


def list_traces(db: Session, task_id: int) -> list[TaskTrace]:
    return list(
        db.scalars(
            select(TaskTrace)
            .where(TaskTrace.task_id == task_id, TaskTrace.deleted == 0)
            .order_by(TaskTrace.seq, TaskTrace.id)
        ).all()
    )


def add_trace(db: Session, task: Task, body, user: User) -> TaskTrace:
    rows = list_traces(db, task.id)
    seq = body.seq or (max((r.seq for r in rows), default=0) + 1)
    row = TaskTrace(
        task_id=task.id,
        node_code=body.node_code,
        node_name=body.node_name or TRACE_NODE_CN.get(body.node_code, body.node_code),
        seq=seq,
        happen_at=body.happen_at or datetime.now(),
        ref_no=body.ref_no,
        operator_id=user.id,
        operator_name=user.name or "",
        remark=body.remark,
    )
    db.add(row)
    db.flush()
    return row


def operation_flow(db: Session, task: Task) -> dict:
    """任务的操作流程图：工序节点 + 追溯节点 + 状态轨迹。

    前端直接渲染成流程链路；审批流另走 approval 域的 timeline。
    """
    processes = list_processes(db, task.id)
    traces = list_traces(db, task.id)
    nodes: list[dict] = []
    for p in processes:
        nodes.append(
            {
                "type": "process",
                "code": p.process_code,
                "name": p.process_name or p.process_code,
                "status": p.status,
                "statusText": _text(PROCESS_STATUS_CN, p.status),
                "seq": p.seq,
                "plannedStart": p.planned_start.strftime("%Y-%m-%d") if p.planned_start else "",
                "plannedEnd": p.planned_end.strftime("%Y-%m-%d") if p.planned_end else "",
                "actualStart": p.actual_start.strftime("%Y-%m-%d %H:%M") if p.actual_start else "",
                "actualEnd": p.actual_end.strftime("%Y-%m-%d %H:%M") if p.actual_end else "",
                "operatorName": p.operator_name,
                "remark": p.remark,
            }
        )
    for t in traces:
        nodes.append(
            {
                "type": "trace",
                "code": t.node_code,
                "name": t.node_name or TRACE_NODE_CN.get(t.node_code, t.node_code),
                "status": "done" if t.happen_at else "pending",
                "statusText": "已发生" if t.happen_at else "待发生",
                "seq": t.seq,
                "happenAt": t.happen_at.strftime("%Y-%m-%d %H:%M") if t.happen_at else "",
                "refNo": t.ref_no,
                "operatorName": t.operator_name,
                "remark": t.remark,
            }
        )
    nodes.sort(key=lambda n: (0 if n["type"] == "process" else 1, n["seq"]))
    current = next((n for n in nodes if n["type"] == "process" and n["status"] == "running"), None)
    return {
        "taskId": task.id,
        "taskNo": task.task_no or "",
        "taskName": task.task_name,
        "status": task.status,
        "processStage": task.process_stage,
        "processStageText": GROUP_CN.get(task.process_stage, task.process_stage),
        "currentNode": current,
        "nodes": nodes,
        "total": len(nodes),
    }


def process_out(p: TaskProcess) -> dict:
    return {
        "id": p.id,
        "taskId": p.task_id,
        "seq": p.seq,
        "processCode": p.process_code,
        "processName": p.process_name,
        "status": p.status,
        "statusText": _text(PROCESS_STATUS_CN, p.status),
        "isCurrent": bool(p.is_current),
        "plannedStart": p.planned_start.strftime("%Y-%m-%d") if p.planned_start else "",
        "plannedEnd": p.planned_end.strftime("%Y-%m-%d") if p.planned_end else "",
        "actualStart": p.actual_start.strftime("%Y-%m-%d %H:%M:%S") if p.actual_start else "",
        "actualEnd": p.actual_end.strftime("%Y-%m-%d %H:%M:%S") if p.actual_end else "",
        "operatorId": p.operator_id,
        "operatorName": p.operator_name,
        "deptId": p.dept_id,
        "deptName": p.dept_name,
        "remark": p.remark,
    }


def assignment_out(a: TaskAssignment) -> dict:
    return {
        "id": a.id,
        "taskId": a.task_id,
        "dimension": a.dimension,
        "dimensionText": _text(DIMENSION_CN, a.dimension),
        "resourceId": a.resource_id,
        "resourceCode": a.resource_code,
        "resourceName": a.resource_name,
        "qty": float(a.qty or 0),
        "unit": a.unit,
        "status": a.status,
        "statusText": _text(ASSIGNMENT_STATUS_CN, a.status),
        "assignerId": a.assigner_id,
        "assignerName": a.assigner_name,
        "plannedAt": a.planned_at.strftime("%Y-%m-%d %H:%M:%S") if a.planned_at else "",
        "confirmedAt": a.confirmed_at.strftime("%Y-%m-%d %H:%M:%S") if a.confirmed_at else "",
        "remark": a.remark,
    }


def trace_out(t: TaskTrace) -> dict:
    return {
        "id": t.id,
        "taskId": t.task_id,
        "nodeCode": t.node_code,
        "nodeName": t.node_name,
        "nodeText": TRACE_NODE_CN.get(t.node_code, t.node_code),
        "seq": t.seq,
        "happenAt": t.happen_at.strftime("%Y-%m-%d %H:%M:%S") if t.happen_at else "",
        "refNo": t.ref_no,
        "operatorId": t.operator_id,
        "operatorName": t.operator_name,
        "remark": t.remark,
    }


def today() -> date:
    return date.today()
