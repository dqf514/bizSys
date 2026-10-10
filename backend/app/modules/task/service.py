"""任务服务：字典标签、状态机、分配通知。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import TaskAssigned, publish
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import DictItem, Notify
from app.modules.auth.models import User
from app.modules.task.models import Task, TaskItem, TaskSample

# action: (允许的前置状态, 目标状态或 None=动态)
TRANSITIONS: dict[str, tuple[set[str], str | None]] = {
    "submit": ({"draft"}, "assigning"),
    "start": ({"assigning", "assigned"}, None),  # assigning→assigned→in_progress 两步
    "finish": ({"in_progress"}, "finished"),
    "close": ({"finished"}, "closed"),
    "stop": ({"draft", "assigning", "assigned", "in_progress", "finished"}, "stopped"),
}

TERMINAL = {"closed", "stopped", "approved", "settled"}


def _check_reports_sealed(db: Session, task: Task) -> None:
    """结束门禁：need_report=1 的条目必须全部签章完成（report_status=sealed）。"""
    rows = db.scalars(
        select(TaskItem).where(
            TaskItem.task_id == task.id,
            TaskItem.deleted == 0,
            TaskItem.need_report == 1,
            TaskItem.report_status != "sealed",
        )
    ).all()
    if rows:
        names = "、".join(f"{i.name or i.item_code}({i.report_no})" for i in rows)
        raise BizException(R.TASK_REPORT_UNFINISHED, f"以下条目报告未完成签章，任务不能结束：{names}")


def mark_settled(db: Session, task: Task) -> Task:
    """closed → settled：由财务模块创建结算单时触发（终态之一）。"""
    if task.status != "closed":
        raise BizException(R.TASK_INVALID_STATE, f"状态「{task.status}」不允许结算")
    task.status = "settled"
    task.version += 1
    task.update_time = datetime.now()
    return task


def dict_labels(db: Session, dict_code: str) -> dict[str, str]:
    rows = db.scalars(
        select(DictItem).where(
            DictItem.dict_type_code == dict_code,
            DictItem.status == "enabled",
            DictItem.deleted == 0,
        )
    )
    return {r.value: r.label for r in rows}


def transition(db: Session, task: Task, action: str, user: User) -> Task:
    spec = TRANSITIONS.get(action)
    if not spec:
        raise BizException(R.GENERIC_PARAM, f"未知动作：{action}")
    allowed, target = spec
    if task.status not in allowed:
        raise BizException(R.TASK_INVALID_STATE, f"状态「{task.status}」不允许执行「{action}」")
    if action == "start":
        target = "assigned" if task.status == "assigning" else "in_progress"
    if action == "close":
        _check_reports_sealed(db, task)
    old = task.status
    task.status = target
    task.version += 1
    task.update_time = datetime.now()
    if action == "submit":
        _notify_assignment(db, task, user)
        publish(TaskAssigned(task_id=task.id, task_no=task.task_no, dept_id=task.dept_id,
                             operator_id=user.id, db=db))
    elif action == "start" and old == "assigning":
        # 接单确认也提醒负责人
        if task.owner_id:
            _add_notify(
                db,
                task.owner_id,
                f"任务已接单：{task.task_no}",
                task,
            )
    return task


def _add_notify(db: Session, user_id: int, title: str, task: Task) -> None:
    db.add(
        Notify(
            user_id=user_id,
            title=title,
            content=f"{task.task_name}（{task.customer_name}）",
            biz_type="task",
            biz_id=task.id,
            link=f"/task/tasks?id={task.id}",
        )
    )


def _notify_assignment(db: Session, task: Task, operator: User) -> None:
    """提交分配 → 站内通知本部门在用用户；无人则通知负责人。"""
    targets = []
    if task.dept_id:
        targets = list(
            db.scalars(
                select(User.id).where(User.dept_id == task.dept_id, User.status == "enabled", User.deleted == 0)
            ).all()
        )
    if not targets and task.owner_id:
        targets = [task.owner_id]
    for uid in dict.fromkeys(targets):
        if uid == operator.id:
            continue
        _add_notify(db, uid, f"新任务分配：{task.task_no}", task)


def sync_items(db: Session, task: Task, items) -> None:
    """整体替换子条目（按 id 保留）。"""
    keep_ids = {i.id for i in items if i.id}
    for old in list(task.items):
        if old.id not in keep_ids:
            db.delete(old)
    existing = {i.id: i for i in task.items}
    order = 1
    for body in items:
        row = existing.get(body.id) if body.id else None
        if row is None:
            row = TaskItem(task_id=task.id)
            db.add(row)
            task.items.append(row)
        row.item_code = body.item_code or f"{order:02d}"
        row.name = body.name
        row.std = body.std
        row.dept = body.dept
        row.inspector = body.inspector
        row.qty = body.qty
        row.settle_type = body.settle_type
        row.need_report = body.need_report
        if body.need_report and not row.report_no:
            from app.services.numbering import next_no

            row.report_no = next_no(db, "report")
            row.report_status = row.report_status or "pending"
        if not body.need_report:
            row.report_status = ""
        if body.report_no:
            row.report_no = body.report_no
        order += 1
    db.flush()


def sync_samples(db: Session, task: Task, samples) -> None:
    keep_ids = {s.id for s in samples if s.id}
    for old in list(task.samples):
        if old.deleted:
            continue  # 已逻辑删除的留底：其 sample_no 永久占用，永不复用
        if old.id not in keep_ids:
            db.delete(old)
            task.samples.remove(old)  # 同步内存集合，避免响应带出已删行
    existing = {s.id: s for s in task.samples}
    for body in samples:
        row = existing.get(body.id) if body.id else None
        if row is None:
            db.flush()  # autoflush=False：让 next_sample_no 看到本批已新增行
            row = TaskSample(task_id=task.id, sample_no=next_sample_no(db, task))
            db.add(row)
            task.samples.append(row)
        row.name = body.name
        row.model = body.model
        row.vin = body.vin
        row.vehicle_type = body.vehicle_type
        row.sample_date = body.sample_date
        row.in_stock = body.in_stock
    db.flush()


def next_sample_no(db: Session, task: Task) -> str:
    """取同任务历史最大位次（含逻辑删除行）+1：sample_no 有唯一索引，删样品后再加不能撞号。"""
    prefix = f"{task.task_no}-"
    nos = db.scalars(select(TaskSample.sample_no).where(TaskSample.task_id == task.id)).all()
    seqs = [int(no[len(prefix):]) for no in nos if no.startswith(prefix) and no[len(prefix):].isdigit()]
    return f"{prefix}{max(seqs, default=0) + 1:02d}"
