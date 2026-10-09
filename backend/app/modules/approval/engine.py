"""审批引擎核心：start / approve / reject / withdraw / add_sign / transfer。

语义（ADR-0002）：
- 顺序多级节点，同节点或签（任一 pending 被同意即过，其余 cancel）；
- 同意到末节点 → instance=approved → 发布 ApprovalCompleted（同事务）；
- 驳回意见必填 → instance=rejected → 发布 ApprovalRejected；
- 撤回仅发起人且尚无人处理；
- 加签：当前节点追加审批人（仍或签）；转办：改派当前待办。
"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import ApprovalCompleted, ApprovalRejected, publish
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import Role, UserRole
from app.modules.approval.models import (
    ApprovalDefinition,
    ApprovalInstance,
    ApprovalNode,
    ApprovalRecord,
    ApprovalTask,
)
from app.modules.auth.models import User


def _resolve_assignees(db: Session, node: ApprovalNode) -> list[User]:
    """按节点配置解析审批人（USER=用户ID，ROLE=角色code，逗号分隔多人）。"""
    values = [v.strip() for v in node.approver_value.replace("，", ",").split(",") if v.strip()]
    if not values:
        return []
    if node.approver_type == "USER":
        ids = [int(v) for v in values if v.isdigit()]
        if not ids:
            return []
        stmt = select(User).where(User.id.in_(ids), User.status == "enabled", User.deleted == 0)
    elif node.approver_type == "ROLE":
        stmt = (
            select(User)
            .join(UserRole, UserRole.user_id == User.id)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                Role.code.in_(values),
                Role.status == "enabled",
                User.status == "enabled",
                User.deleted == 0,
                UserRole.deleted == 0,
            )
        )
    else:
        return []
    return list(db.scalars(stmt).unique().all())


def _record(
    db: Session,
    instance: ApprovalInstance,
    action: str,
    operator: User,
    comment: str = "",
    node_name: str = "",
    seq: int = 0,
) -> None:
    instance.records.append(  # 走关系追加，保证已加载集合同步
        ApprovalRecord(
            instance_id=instance.id,
            seq=seq or instance.current_seq,
            node_name=node_name,
            action=action,
            operator_id=operator.id,
            operator_name=operator.name or operator.username,
            comment=comment or "",
        )
    )


def _cancel_pending(db: Session, instance_id: int, seq: int | None = None) -> None:
    stmt = select(ApprovalTask).where(
        ApprovalTask.instance_id == instance_id,
        ApprovalTask.status == "pending",
        ApprovalTask.deleted == 0,
    )
    if seq is not None:
        stmt = stmt.where(ApprovalTask.seq == seq)
    for t in db.scalars(stmt):
        t.status = "cancelled"


def _activate_node(db: Session, instance: ApprovalInstance, node: ApprovalNode) -> None:
    assignees = _resolve_assignees(db, node)
    if not assignees:
        raise BizException(R.GENERIC_PARAM, f"节点「{node.node_name or node.seq}」未配置可用审批人")
    for u in assignees:
        db.add(
            ApprovalTask(
                instance_id=instance.id,
                seq=node.seq,
                node_name=node.node_name or f"第{node.seq}节点",
                assignee_id=u.id,
                assignee_name=u.name or u.username,
                status="pending",
            )
        )
    instance.current_seq = node.seq
    instance.update_time = datetime.now()
    db.flush()  # autoflush=False：同事务内后续查询要能看到新待办


def start(
    db: Session,
    *,
    biz_type: str,
    biz_id: int,
    definition_code: str,
    title: str,
    initiator: User,
    form_snapshot: dict | None = None,
) -> ApprovalInstance:
    """发起审批（业务模块唯一入口之一）。已存在 running 实例 → 70004。"""
    running = db.scalar(
        select(ApprovalInstance).where(
            ApprovalInstance.biz_type == biz_type,
            ApprovalInstance.biz_id == biz_id,
            ApprovalInstance.status == "running",
            ApprovalInstance.deleted == 0,
        )
    )
    if running:
        raise BizException(R.APPROVAL_INSTANCE_RUNNING)

    definition = db.scalar(
        select(ApprovalDefinition).where(
            ApprovalDefinition.code == definition_code,
            ApprovalDefinition.enabled == 1,
            ApprovalDefinition.deleted == 0,
        )
    )
    if not definition:
        raise BizException(R.GENERIC_NOT_FOUND, f"流程定义不存在或未启用：{definition_code}")
    nodes = [n for n in definition.nodes if n.deleted == 0]
    if not nodes:
        raise BizException(R.GENERIC_PARAM, f"流程定义未配置节点：{definition_code}")

    instance = ApprovalInstance(
        biz_type=biz_type,
        biz_id=biz_id,
        definition_id=definition.id,
        definition_code=definition.code,
        title=title or "",
        status="running",
        current_seq=nodes[0].seq,
        initiator_id=initiator.id,
        initiator_name=initiator.name or initiator.username,
        form_snapshot=json.dumps(form_snapshot, ensure_ascii=False) if form_snapshot else None,
    )
    db.add(instance)
    db.flush()
    _activate_node(db, instance, nodes[0])
    _record(db, instance, "start", initiator, comment="提交审批", node_name=nodes[0].node_name, seq=nodes[0].seq)
    return instance


def _get_open_task(db: Session, task_id: int, user: User) -> ApprovalTask:
    task = db.get(ApprovalTask, task_id)
    if not task or task.deleted or task.status != "pending":
        raise BizException(R.APPROVAL_NO_TODO)
    if task.assignee_id != user.id:
        raise BizException(R.APPROVAL_NOT_ASSIGNEE)
    return task


def _load_running(db: Session, task: ApprovalTask) -> tuple[ApprovalInstance, list[ApprovalNode]]:
    instance = db.get(ApprovalInstance, task.instance_id)
    if not instance or instance.deleted or instance.status != "running":
        raise BizException(R.APPROVAL_INVALID_STATE)
    definition = db.get(ApprovalDefinition, instance.definition_id) if instance.definition_id else None
    nodes = [n for n in (definition.nodes if definition else []) if n.deleted == 0]
    return instance, nodes


def _advance(db: Session, instance: ApprovalInstance, nodes: list[ApprovalNode], operator: User) -> None:
    """当前节点已通过 → 激活下一节点或完成实例。"""
    following = sorted([n for n in nodes if n.seq > instance.current_seq], key=lambda n: n.seq)
    if not following:
        instance.status = "approved"
        instance.finished_at = datetime.now()
        db.flush()
        publish(
            ApprovalCompleted(
                biz_type=instance.biz_type,
                biz_id=instance.biz_id,
                instance_id=instance.id,
                operator_id=operator.id,
                db=db,
            )
        )
    else:
        _activate_node(db, instance, following[0])


def approve(db: Session, task_id: int, user: User, comment: str = "") -> ApprovalInstance:
    task = _get_open_task(db, task_id, user)
    instance, nodes = _load_running(db, task)
    task.status = "agreed"
    task.comment = comment or ""
    task.acted_at = datetime.now()
    task.acted_by_id = user.id
    _record(db, instance, "agree", user, comment, node_name=task.node_name, seq=task.seq)
    _cancel_pending(db, instance.id, seq=task.seq)  # 或签：本节点其余待办作废
    _advance(db, instance, nodes, user)
    return instance


def reject(db: Session, task_id: int, user: User, comment: str) -> ApprovalInstance:
    if not (comment or "").strip():
        raise BizException(R.APPROVAL_COMMENT_REQUIRED)
    task = _get_open_task(db, task_id, user)
    instance, _ = _load_running(db, task)
    task.status = "rejected"
    task.comment = comment
    task.acted_at = datetime.now()
    task.acted_by_id = user.id
    _record(db, instance, "reject", user, comment, node_name=task.node_name, seq=task.seq)
    _cancel_pending(db, instance.id)
    instance.status = "rejected"
    instance.finished_at = datetime.now()
    db.flush()
    publish(
        ApprovalRejected(
            biz_type=instance.biz_type,
            biz_id=instance.biz_id,
            instance_id=instance.id,
            operator_id=user.id,
            comment=comment,
            db=db,
        )
    )
    return instance


def withdraw(db: Session, instance_id: int, user: User, comment: str = "") -> ApprovalInstance:
    instance = db.get(ApprovalInstance, instance_id)
    if not instance or instance.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if instance.initiator_id != user.id and "super" not in user.role_codes:
        raise BizException(R.AUTH_FORBIDDEN, http_status=403)
    if instance.status != "running":
        raise BizException(R.APPROVAL_INVALID_STATE)
    # 转办/加签不算"已审"，仅同意或驳回后不可撤回
    acted = db.scalar(
        select(ApprovalTask.id).where(
            ApprovalTask.instance_id == instance.id,
            ApprovalTask.status.in_(("agreed", "rejected")),
            ApprovalTask.deleted == 0,
        )
    )
    if acted:
        raise BizException(R.APPROVAL_INVALID_STATE, "已有审批人处理，不能撤回")
    _cancel_pending(db, instance.id)
    instance.status = "withdrawn"
    instance.finished_at = datetime.now()
    _record(db, instance, "withdraw", user, comment or "发起人撤回")
    db.flush()
    return instance


def add_sign(db: Session, task_id: int, user: User, approver: User, comment: str = "") -> ApprovalInstance:
    task = _get_open_task(db, task_id, user)
    instance, _ = _load_running(db, task)
    if approver.id == user.id:
        raise BizException(R.GENERIC_PARAM, "不能给本人加签")
    exists = db.scalar(
        select(ApprovalTask.id).where(
            ApprovalTask.instance_id == instance.id,
            ApprovalTask.seq == task.seq,
            ApprovalTask.assignee_id == approver.id,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
    )
    if exists:
        raise BizException(R.GENERIC_PARAM, "该审批人已在本节点待办中")
    db.add(
        ApprovalTask(
            instance_id=instance.id,
            seq=task.seq,
            node_name=task.node_name,
            assignee_id=approver.id,
            assignee_name=approver.name or approver.username,
            status="pending",
            task_kind="add_sign",
        )
    )
    _record(
        db,
        instance,
        "add_sign",
        user,
        comment or f"加签：{approver.name or approver.username}",
        node_name=task.node_name,
        seq=task.seq,
    )
    db.flush()
    return instance


def transfer(db: Session, task_id: int, user: User, to_user: User, comment: str = "") -> ApprovalInstance:
    task = _get_open_task(db, task_id, user)
    instance, _ = _load_running(db, task)
    if to_user.id == user.id:
        raise BizException(R.GENERIC_PARAM, "不能转办给自己")
    task.status = "transferred"
    task.comment = comment or ""
    task.acted_at = datetime.now()
    task.acted_by_id = user.id
    db.add(
        ApprovalTask(
            instance_id=instance.id,
            seq=task.seq,
            node_name=task.node_name,
            assignee_id=to_user.id,
            assignee_name=to_user.name or to_user.username,
            status="pending",
        )
    )
    _record(
        db,
        instance,
        "transfer",
        user,
        comment or f"转办给：{to_user.name or to_user.username}",
        node_name=task.node_name,
        seq=task.seq,
    )
    db.flush()
    return instance
