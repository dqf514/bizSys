"""审批引擎核心：start / approve / reject / withdraw / add_sign / transfer。

语义（ADR-0002，F1 合并 TPCworkflow 引擎语义）：
- 节点类型：approval（审批）/ condition（条件分支，按 instance.variables 路由）/ cc（抄送，不阻塞）；
- 审批节点 sign_mode：or（任一通过，其余作废）/ and（全员通过）/ sequential（依次逐个）；
- 同意到末节点 → instance=approved → 发布 ApprovalCompleted（同事务）；
- 驳回意见必填 → instance=rejected → 发布 ApprovalRejected；业务侧重新提交即开新实例（与 TPC 对齐）；
- 撤回仅发起人且尚无人处理 → instance=withdrawn → 发布 ApprovalWithdrawn；
- 加签：当前节点追加审批人；或签节点一人通过后，同节点其他普通或签待办作废，
  但加签待办保留且须处理完毕节点才推进（对齐 TPC workflow_add_sign.py）；
- 转办：改派当前待办；每次状态变化写 approval_record 时间线（含 payload）。
"""

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import (
    ApprovalCompleted,
    ApprovalRejected,
    ApprovalTodoCreated,
    ApprovalWithdrawn,
    publish,
)
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import Role, UserRole
from app.modules.approval.graph import first_seq, parse_json, route_from
from app.modules.approval.models import (
    ApprovalCc,
    ApprovalDefinition,
    ApprovalInstance,
    ApprovalNode,
    ApprovalRecord,
    ApprovalTask,
)
from app.modules.auth.models import User


def _emit_todo(db: Session, instance: ApprovalInstance, assignee: User, node_name: str, operator_id: int = 0) -> None:
    """每个 pending 待办产生时发布 ApprovalTodoCreated（站内/企微通知钩子，ADR-0001 可插拔）。"""
    publish(
        ApprovalTodoCreated(
            biz_type=instance.biz_type,
            biz_id=instance.biz_id,
            instance_id=instance.id,
            title=instance.title or "",
            node_name=node_name,
            assignee_id=assignee.id,
            assignee_name=assignee.name or assignee.username,
            operator_id=operator_id,
            db=db,
        )
    )


def _resolve_assignees(db: Session, node: ApprovalNode) -> list[User]:
    """按节点配置解析审批人/抄送人（USER=用户ID，ROLE=角色code，逗号分隔多人）。"""
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
    payload: dict | None = None,
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
            payload=json.dumps(payload, ensure_ascii=False) if payload else None,
        )
    )


def _cancel_pending(
    db: Session, instance_id: int, seq: int | None = None, keep_add_sign: bool = False
) -> None:
    stmt = select(ApprovalTask).where(
        ApprovalTask.instance_id == instance_id,
        ApprovalTask.status == "pending",
        ApprovalTask.deleted == 0,
    )
    if seq is not None:
        stmt = stmt.where(ApprovalTask.seq == seq)
    for t in db.scalars(stmt):
        if keep_add_sign and t.task_kind == "add_sign":
            continue  # 对齐 TPC cancel_other_or_sign_tasks：加签待办不作废
        t.status = "cancelled"


def _node_finished(db: Session, instance_id: int, seq: int) -> bool:
    """节点无剩余 pending 待办即视为完成（and=全员已审；or=其余已作废；sequential=队列走完）。"""
    pending = db.scalar(
        select(ApprovalTask.id).where(
            ApprovalTask.instance_id == instance_id,
            ApprovalTask.seq == seq,
            ApprovalTask.status == "pending",
            ApprovalTask.deleted == 0,
        )
    )
    return pending is None


def _finish(db: Session, instance: ApprovalInstance, operator: User) -> None:
    instance.status = "approved"
    instance.finished_at = datetime.now()
    instance.current_node_ids = "[]"
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


def _touch_current(instance: ApprovalInstance, seq: int | None) -> None:
    instance.current_seq = seq or 0
    instance.current_node_ids = json.dumps([seq] if seq else [])
    instance.update_time = datetime.now()


def _walk(db: Session, instance: ApprovalInstance, nodes: list[ApprovalNode], seq: int | None, operator: User) -> None:
    """从 seq 起推进流程：condition 路由 / cc 落抄送 / approval 建待办；走到末端则实例通过。"""
    by_seq = {n.seq: n for n in nodes}
    variables = parse_json(instance.variables, {})
    guard = 0
    while seq is not None:
        guard += 1
        if guard > 100:
            raise BizException(R.GENERIC_SYSTEM, "流程路由异常：节点循环")
        node = by_seq.get(seq)
        if node is None:
            break
        if node.node_type == "condition":
            _record(db, instance, "route", operator, node_name=node.node_name, seq=node.seq,
                    payload={"variables": variables} if variables else None)
            seq = route_from(nodes, seq, variables)
            continue
        if node.node_type == "cc":
            recipients = _resolve_assignees(db, node)
            for u in recipients:
                db.add(
                    ApprovalCc(
                        instance_id=instance.id,
                        seq=node.seq,
                        node_name=node.node_name or "抄送",
                        user_id=u.id,
                        user_name=u.name or u.username,
                    )
                )
                _record(db, instance, "cc", u, comment="抄送", node_name=node.node_name, seq=node.seq)
            db.flush()
            seq = route_from(nodes, seq, variables)
            continue
        # approval 节点
        assignees = _resolve_assignees(db, node)
        if not assignees:
            raise BizException(R.GENERIC_PARAM, f"节点「{node.node_name or node.seq}」未配置可用审批人")
        node_name = node.node_name or f"第{node.seq}节点"
        if node.sign_mode == "sequential":
            queue = [u.id for u in assignees]
            first = assignees[0]
            db.add(
                ApprovalTask(
                    instance_id=instance.id,
                    seq=node.seq,
                    node_name=node_name,
                    node_type="approval",
                    assignee_id=first.id,
                    assignee_name=first.name or first.username,
                    status="pending",
                    action_meta=json.dumps(
                        {"sequential_queue": queue, "sequential_index": 0}, ensure_ascii=False
                    ),
                )
            )
            _emit_todo(db, instance, first, node_name, operator.id)
        else:  # or / and：全员同时持有待办
            for u in assignees:
                db.add(
                    ApprovalTask(
                        instance_id=instance.id,
                        seq=node.seq,
                        node_name=node_name,
                        node_type="approval",
                        assignee_id=u.id,
                        assignee_name=u.name or u.username,
                        status="pending",
                    )
                )
                _emit_todo(db, instance, u, node_name, operator.id)
        _touch_current(instance, seq)
        db.flush()  # autoflush=False：同事务内后续查询要能看到新待办
        return
    _touch_current(instance, None)
    _finish(db, instance, operator)


def start(
    db: Session,
    *,
    biz_type: str,
    biz_id: int,
    definition_code: str,
    title: str,
    initiator: User,
    form_snapshot: dict | None = None,
    variables: dict | None = None,
) -> ApprovalInstance:
    """发起审批（业务模块唯一入口之一）。已存在 running 实例 → 70004。"""
    # 行锁兜底：调用方应先锁定业务行（如合同提交已 with_for_update），此处锁已有 running 行防并发双实例
    running = db.scalar(
        select(ApprovalInstance)
        .where(
            ApprovalInstance.biz_type == biz_type,
            ApprovalInstance.biz_id == biz_id,
            ApprovalInstance.status == "running",
            ApprovalInstance.deleted == 0,
        )
        .with_for_update()
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
        current_seq=first_seq(nodes) or 1,
        initiator_id=initiator.id,
        initiator_name=initiator.name or initiator.username,
        form_snapshot=json.dumps(form_snapshot, ensure_ascii=False) if form_snapshot else None,
        variables=json.dumps(variables, ensure_ascii=False) if variables else None,
    )
    db.add(instance)
    db.flush()
    _record(db, instance, "start", initiator, comment="提交审批")
    _walk(db, instance, nodes, first_seq(nodes), initiator)
    return instance


def _get_open_task(db: Session, task_id: int, user: User) -> ApprovalTask:
    # 行锁：或签节点两人同时同意时串行化，后到者看到 status 已变 → 70001
    task = db.get(ApprovalTask, task_id, with_for_update=True)
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


def _node_config(nodes: list[ApprovalNode], seq: int) -> ApprovalNode | None:
    for n in nodes:
        if n.seq == seq:
            return n
    return None


def _spawn_next_sequential(db: Session, task: ApprovalTask) -> bool:
    """依次签：当前人通过后为队列下一人建待办。返回是否还有后继。"""
    meta = parse_json(task.action_meta, {})
    queue = meta.get("sequential_queue")
    idx = meta.get("sequential_index", 0)
    if not queue or idx + 1 >= len(queue):
        return False
    next_uid = queue[idx + 1]
    u = db.get(User, next_uid)
    if not u:
        return False
    db.add(
        ApprovalTask(
            instance_id=task.instance_id,
            seq=task.seq,
            node_name=task.node_name,
            node_type=task.node_type,
            assignee_id=u.id,
            assignee_name=u.name or u.username,
            status="pending",
            action_meta=json.dumps({"sequential_queue": queue, "sequential_index": idx + 1}, ensure_ascii=False),
        )
    )
    instance = db.get(ApprovalInstance, task.instance_id)
    if instance:
        _emit_todo(db, instance, u, task.node_name, task.acted_by_id or 0)
    db.flush()
    return True


def approve(db: Session, task_id: int, user: User, comment: str = "") -> ApprovalInstance:
    task = _get_open_task(db, task_id, user)
    instance, nodes = _load_running(db, task)
    task.status = "agreed"
    task.comment = comment or ""
    task.acted_at = datetime.now()
    task.acted_by_id = user.id
    _record(db, instance, "agree", user, comment, node_name=task.node_name, seq=task.seq)

    node = _node_config(nodes, task.seq)
    sign_mode = node.sign_mode if node else "or"
    if sign_mode == "sequential" and task.task_kind == "sign":
        _spawn_next_sequential(db, task)
    elif sign_mode == "or":
        # 或签：一人通过后同节点其他普通或签待办作废；加签待办保留并阻塞节点推进
        _cancel_pending(db, instance.id, seq=task.seq, keep_add_sign=True)

    db.flush()  # autoflush=False：先把状态变更落库，节点完成判定才看得到
    if _node_finished(db, instance.id, task.seq):
        variables = parse_json(instance.variables, {})
        _walk(db, instance, nodes, route_from(nodes, task.seq, variables), user)
    else:
        db.flush()
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
    instance.current_node_ids = "[]"
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
    instance.current_node_ids = "[]"
    instance.finished_at = datetime.now()
    _record(db, instance, "withdraw", user, comment or "发起人撤回")
    db.flush()
    publish(
        ApprovalWithdrawn(
            biz_type=instance.biz_type,
            biz_id=instance.biz_id,
            instance_id=instance.id,
            operator_id=user.id,
            db=db,
        )
    )
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
            node_type=task.node_type,
            assignee_id=approver.id,
            assignee_name=approver.name or approver.username,
            status="pending",
            task_kind="add_sign",
            action_meta=json.dumps({"add_sign": True, "requested_by": user.id}, ensure_ascii=False),
        )
    )
    _emit_todo(db, instance, approver, task.node_name, user.id)
    _record(
        db,
        instance,
        "add_sign",
        user,
        comment or f"加签：{approver.name or approver.username}",
        node_name=task.node_name,
        seq=task.seq,
        payload={"approverId": approver.id},
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
            node_type=task.node_type,
            assignee_id=to_user.id,
            assignee_name=to_user.name or to_user.username,
            status="pending",
        )
    )
    _emit_todo(db, instance, to_user, task.node_name, user.id)
    _record(
        db,
        instance,
        "transfer",
        user,
        comment or f"转办给：{to_user.name or to_user.username}",
        node_name=task.node_name,
        seq=task.seq,
        payload={"toUserId": to_user.id},
    )
    db.flush()
    return instance
