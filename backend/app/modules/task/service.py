"""任务服务：字典标签、状态机、分配通知、立项流程事件订阅。"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import (
    ApprovalCompleted,
    ApprovalRejected,
    ApprovalWithdrawn,
    TaskAssigned,
    publish,
    subscribe,
)
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import DictItem, Notify
from app.modules.auth.models import User
from app.modules.task.models import Task, TaskItem, TaskSample

# action: (允许的前置状态, 目标状态或 None=动态)
# 精简状态机（2026-10-21 评审）：assigning/assigned 并入 in_progress，closed 并入 finished
TRANSITIONS: dict[str, tuple[set[str], str | None]] = {
    "submit": ({"draft", "rejected"}, None),  # 绑定立项定义→approving；未绑定直通 in_progress
    "finish": ({"in_progress"}, "finished"),  # 完成门禁：需报告条目全部签章
    "stop": ({"draft", "approving", "rejected", "in_progress", "finished"}, "stopped"),
}


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
    """finished → settled：由财务模块创建结算单时触发（终态之一）。"""
    if task.status != "finished":
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
    if action == "submit":
        return _submit(db, task, user)
    if action == "finish":
        _check_reports_sealed(db, task)
    task.status = target
    task.version += 1
    task.update_time = datetime.now()
    return task


def _snapshot(t: Task) -> dict:
    return json.loads(
        json.dumps(
            {
                "taskNo": t.task_no,
                "taskName": t.task_name,
                "taskType": t.task_type,
                "bizBlock": t.biz_block,
                "customerName": t.customer_name,
                "contractNo": t.contract_no,
                "ownerName": t.owner_name,
                "planFinishDate": t.plan_finish_date.isoformat() if t.plan_finish_date else "",
            },
            ensure_ascii=False,
            default=str,
        )
    )


def _enter_in_progress(db: Session, task: Task, operator: User) -> None:
    """立项通过/直通后的共同路径：in_progress（分配执行中）+ 分配通知 + TaskAssigned 事件。"""
    task.status = "in_progress"
    task.version += 1
    task.update_time = datetime.now()
    _notify_assignment(db, task, operator)
    publish(TaskAssigned(task_id=task.id, task_no=task.task_no, dept_id=task.dept_id,
                         operator_id=operator.id, db=db))


def _submit(db: Session, task: Task, user: User) -> Task:
    """提交 = 发放正式编号（任务/样品/报告）+ 发起任务立项流程；未绑定 task 定义时直通（不产生审批等待）。"""
    from app.modules.approval import service as approval_svc
    from app.services.numbering import next_no

    if not task.task_no:
        # 首次提交才发号；驳回/撤回后重提沿用（同合同 contract_no）
        task.task_no = next_no(db, "task", category=task.task_type or None)
        db.flush()
    for s in task.samples:
        if not s.deleted and not s.sample_no:
            s.sample_no = next_sample_no(db, task)
            db.flush()
    for i in task.items:
        if not i.deleted and i.need_report and not i.report_no:
            i.report_no = next_no(db, "report")
            i.report_status = i.report_status or "pending"
    db.flush()

    definition = approval_svc.resolve_definition(db, "task")
    if not definition:
        _enter_in_progress(db, task, user)
        return task
    inst = approval_svc.start(
        db,
        biz_type="task",
        biz_id=task.id,
        definition_code=definition.code,
        title=f"{task.task_no} {task.task_name}",
        initiator=user,
        form_snapshot=_snapshot(task),
        variables={
            "task_type": task.task_type,
            "biz_block": task.biz_block,
            "customer_name": task.customer_name,
        },
    )
    task.status = "approving"
    task.flow_instance_id = inst.id
    task.version += 1
    task.update_time = datetime.now()
    return task


def _handle_completed(event: ApprovalCompleted) -> None:
    """立项审批通过 → 任务生效（in_progress，走分配通知）。"""
    if event.biz_type != "task":
        return
    db: Session = event.db
    t = db.get(Task, event.biz_id)
    if not t or t.deleted or t.status != "approving":
        return
    operator = db.get(User, event.operator_id)
    t.flow_instance_id = event.instance_id
    _enter_in_progress(db, t, operator or User(id=event.operator_id))


def _handle_rejected(event: ApprovalRejected) -> None:
    if event.biz_type != "task":
        return
    db: Session = event.db
    t = db.get(Task, event.biz_id)
    if not t or t.deleted or t.status != "approving":
        return
    t.status = "rejected"  # 可修改后重新提交（开新实例）
    t.flow_instance_id = event.instance_id
    t.version += 1
    t.update_time = datetime.now()


def _handle_withdrawn(event: ApprovalWithdrawn) -> None:
    if event.biz_type != "task":
        return
    db: Session = event.db
    t = db.get(Task, event.biz_id)
    if not t or t.deleted or t.status != "approving":
        return
    t.status = "draft"
    t.flow_instance_id = event.instance_id
    t.version += 1
    t.update_time = datetime.now()


subscribe(ApprovalCompleted, _handle_completed)
subscribe(ApprovalRejected, _handle_rejected)
subscribe(ApprovalWithdrawn, _handle_withdrawn)


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
        if body.need_report and not row.report_no and task.task_no:
            # 草稿不占报告编号：任务提交时统一发放（见 _submit）
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
            # 草稿任务无编号 → 样品同步无编号，提交时统一发放
            row = TaskSample(task_id=task.id, sample_no=next_sample_no(db, task) if task.task_no else None)
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
    seqs = [int(no[len(prefix):]) for no in nos if no and no.startswith(prefix) and no[len(prefix):].isdigit()]
    return f"{prefix}{max(seqs, default=0) + 1:02d}"
