"""审批引擎核心：start / approve / reject / withdraw / add_sign / transfer。

语义（ADR-0002，F1 合并 TPCworkflow 引擎语义）：
- 节点类型：approval（审批）/ condition（条件分支，按 instance.variables 路由）/ cc（抄送，不阻塞）/
  executor（办理，E1 企业微信移植：产生待办由办理人处理，任一办理人处理即推进）；
- 审批节点 sign_mode：or（任一通过，其余作废）/ and（全员通过）/ sequential（依次逐个）；
- 同意到末节点 → instance=approved → 发布 ApprovalCompleted（同事务）；
- 驳回意见必填 → instance=rejected → 发布 ApprovalRejected；业务侧重新提交即开新实例（与 TPC 对齐）；
- 撤回仅发起人且尚无人处理 → instance=withdrawn → 发布 ApprovalWithdrawn；
- 加签：当前节点追加审批人；或签节点一人通过后，同节点其他普通或签待办作废，
  但加签待办保留且须处理完毕节点才推进（对齐 TPC workflow_add_sign.py）；
- 转办：改派当前待办；每次状态变化写 approval_record 时间线（含 payload）。
- 流程通用选项（ApprovalDefinition.options，E1）：意见必填 / 办理意见必填 / 允许加签 /
  通过后可撤销 —— 未配置时**保持既有行为**。
"""

import json
from dataclasses import dataclass
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
from app.modules.admin import org
from app.modules.admin.models import Dept, Role, UserRole
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

# 组织审批人类型：按发起人部门任职解析（approver_value 转为兜底角色 code，可空）
ORG_APPROVER_TYPES = ("DEPT_LEADER", "PARENT_DEPT_LEADER", "SUPERVISOR_CHAIN")

# 表单字段审批人类型（F6）：approver_value 是**流程变量名**，值从 instance.variables 取。
# 解决"审批人每单不同"的场景（门户访客预约的被访人），因为 USER/ROLE 是流程定义里写死的，
# 而组织类型按**发起人**部门解析 —— 门户发起人不是 sys_user，必然解析失败。
FORM_APPROVER_TYPES = ("FORM_USER", "FORM_ROLE", "FORM_DEPT_LEADER")


@dataclass(frozen=True)
class FlowInitiator:
    """外部发起人适配器（门户合作方等**非 sys_user** 的发起人）。

    引擎只取发起人的 `id` / `name` / `username`（duck-typing），因此外部发起人无需
    落到 `sys_user` 即可发起流程：`initiator_id = 0` 表示"系统外部"，
    审批中心的「我发起的」按 `initiator_id == 当前用户` 过滤，天然不包含外部单据。
    """

    id: int = 0
    name: str = ""
    username: str = ""


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


def _resolve_role_users(db: Session, value: str) -> list[User]:
    """按角色 code（逗号分隔）解析 enabled 用户；空值返回空。"""
    values = [v.strip() for v in value.replace("，", ",").split(",") if v.strip()]
    if not values:
        return []
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
    return list(db.scalars(stmt).unique().all())


def _resolve_org_assignees(db: Session, node: ApprovalNode, initiator_id: int) -> tuple[list[User], list[str]]:
    """组织审批人解析（对齐 TPC assignee_resolver）：

    - DEPT_LEADER：发起人主部门负责人；PARENT_DEPT_LEADER：主部门的上级部门负责人；
    - SUPERVISOR_CHAIN：从主部门负责人起逐级向上（chain_levels 级，空/0=到根），有序去重；
    - 发起人被排除（避免自审）；无负责人/无上级的级跳过并返回说明（调用方写时间线兜底）。
    """
    if not initiator_id:
        return [], ["缺少发起人，无法解析组织审批人"]
    dept_id = org.primary_dept_id(db, initiator_id)
    if not dept_id:
        return [], ["发起人未设置主部门任职"]
    notes: list[str] = []
    ids: list[int] = []
    if node.approver_type == "DEPT_LEADER":
        ids = org.dept_leader_ids(db, dept_id, exclude_user_id=initiator_id)
        if not ids:
            notes.append("发起人主部门无可用负责人")
    elif node.approver_type == "PARENT_DEPT_LEADER":
        dept = db.get(Dept, dept_id)
        parent_id = dept.parent_id if dept and not dept.deleted else None
        if not parent_id:
            return [], ["发起人主部门无上级部门"]
        ids = org.dept_leader_ids(db, parent_id, exclude_user_id=initiator_id)
        if not ids:
            notes.append("上级部门无可用负责人")
    else:  # SUPERVISOR_CHAIN
        ids, notes = org.leader_chain(db, dept_id, levels=node.chain_levels or 0, exclude_user_id=initiator_id)
    if not ids:
        return [], notes or ["未解析到组织审批人"]
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids))).all()}
    return [users[i] for i in ids if i in users], notes


def _form_value(node: ApprovalNode, variables: dict | None) -> str:
    """取表单变量值：approver_value 是变量名；变量不存在时回退为字面量。"""
    variables = variables or {}
    key = (node.approver_value or "").strip()
    if key in variables:
        v = variables[key]
        if isinstance(v, bool):
            return ""
        if isinstance(v, (list, tuple, set)):
            return ",".join(str(x) for x in v)
        return str(v)
    return key


def _resolve_form_assignees(
    db: Session, node: ApprovalNode, variables: dict | None
) -> tuple[list[User], list[str]]:
    """按流程变量解析审批人（F6 表单字段审批人）。

    - FORM_USER：变量值为用户 id（逗号分隔多人）；
    - FORM_ROLE：变量值为角色 code（逗号分隔多人）；
    - FORM_DEPT_LEADER：变量值为部门 id，取该部门负责人。
    """
    raw = _form_value(node, variables)
    values = [v.strip() for v in raw.replace("，", ",").split(",") if v.strip()]
    var_name = (node.approver_value or "").strip()
    if not values:
        return [], [f"流程变量「{var_name}」未提供审批人"]
    if node.approver_type == "FORM_USER":
        ids = [int(v) for v in values if v.isdigit()]
        if not ids:
            return [], [f"流程变量「{var_name}」不是合法的用户 id"]
        stmt = select(User).where(User.id.in_(ids), User.status == "enabled", User.deleted == 0)
        users = list(db.scalars(stmt).unique().all())
        if not users:
            return [], [f"流程变量「{var_name}」指向的用户不存在或已停用"]
        return users, []
    if node.approver_type == "FORM_ROLE":
        users = _resolve_role_users(db, ",".join(values))
        if not users:
            return [], [f"流程变量「{var_name}」指向的角色无可用人员"]
        return users, []
    # FORM_DEPT_LEADER
    ids: list[int] = []
    for v in values:
        if not v.isdigit():
            continue
        ids.extend(org.dept_leader_ids(db, int(v)))
    if not ids:
        return [], [f"流程变量「{var_name}」指向的部门无可用负责人"]
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(ids))).all()}
    return [users[i] for i in ids if i in users], []


def _resolve_assignees(
    db: Session, node: ApprovalNode, initiator_id: int = 0, variables: dict | None = None
) -> tuple[list[User], list[str]]:
    """按节点配置解析审批人/抄送人，返回 (用户列表, 解析说明)。

    USER=用户ID，ROLE=角色code（逗号分隔多人）；组织类型按发起人部门任职解析；
    FORM_* 类型按流程变量（instance.variables）解析。
    """
    if node.approver_type in ORG_APPROVER_TYPES:
        return _resolve_org_assignees(db, node, initiator_id)
    if node.approver_type in FORM_APPROVER_TYPES:
        return _resolve_form_assignees(db, node, variables)
    values = [v.strip() for v in node.approver_value.replace("，", ",").split(",") if v.strip()]
    if not values:
        return [], []
    if node.approver_type == "USER":
        ids = [int(v) for v in values if v.isdigit()]
        if not ids:
            return [], []
        stmt = select(User).where(User.id.in_(ids), User.status == "enabled", User.deleted == 0)
        return list(db.scalars(stmt).unique().all()), []
    if node.approver_type == "ROLE":
        return _resolve_role_users(db, node.approver_value), []
    return [], []


def _resolve_with_fallback(
    db: Session, instance: ApprovalInstance, node: ApprovalNode, operator: User
) -> list[User] | None:
    """解析失败时的兜底：组织类型转兜底角色；表单字段类型直接跳过节点。

    返回 None 表示节点被跳过（调用方继续路由）；否则返回可用用户列表。
    """
    variables = parse_json(instance.variables, {})
    assignees, notes = _resolve_assignees(db, node, instance.initiator_id, variables)
    if node.approver_type in FORM_APPROVER_TYPES:
        # 表单变量没解析出审批人：写时间线并跳过本节点（不卡死流程，也不硬失败提交）
        if not assignees:
            _record(
                db,
                instance,
                "auto_pass",
                operator,
                comment="；".join(notes) or "未从流程变量解析到审批人，节点自动通过",
                node_name=node.node_name,
                seq=node.seq,
            )
            return None
        if notes:
            _record(
                db, instance, "fallback", operator, comment="；".join(notes),
                node_name=node.node_name, seq=node.seq,
            )
        return assignees
    if node.approver_type not in ORG_APPROVER_TYPES:
        return assignees
    if not assignees:
        fallback = _resolve_role_users(db, node.approver_value)
        if fallback:
            notes.append(f"组织审批人解析失败，转兜底角色：{node.approver_value}")
            assignees = fallback
        else:
            _record(
                db,
                instance,
                "auto_pass",
                operator,
                comment="；".join(notes) or "未解析到审批人，节点自动通过",
                node_name=node.node_name,
                seq=node.seq,
            )
            return None
    if notes:
        _record(db, instance, "fallback", operator, comment="；".join(notes), node_name=node.node_name, seq=node.seq)
    return assignees


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
            recipients = _resolve_with_fallback(db, instance, node, operator)
            if recipients is None:  # 组织类型解析失败且无兜底：跳过抄送节点
                seq = route_from(nodes, seq, variables)
                continue
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
        # approval / executor 节点
        assignees = _resolve_with_fallback(db, instance, node, operator)
        if assignees is None:  # 组织类型解析失败且无兜底角色：节点自动通过，不卡死流程
            seq = route_from(nodes, seq, variables)
            continue
        if not assignees:
            raise BizException(R.GENERIC_PARAM, f"节点「{node.node_name or node.seq}」未配置可用审批人")
        is_executor = node.node_type == "executor"
        task_type = "executor" if is_executor else "approval"
        node_name = node.node_name or (f"办理{node.seq}" if is_executor else f"第{node.seq}节点")
        if node.sign_mode == "sequential" or node.approver_type == "SUPERVISOR_CHAIN":
            # SUPERVISOR_CHAIN 复用 sequential 语义：逐级链条每级一个顺序待办
            queue = [u.id for u in assignees]
            first = assignees[0]
            db.add(
                ApprovalTask(
                    instance_id=instance.id,
                    seq=node.seq,
                    node_name=node_name,
                    node_type=task_type,
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
                        node_type=task_type,
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
    definition_code: str = "",
    definition_id: int | None = None,
    title: str,
    initiator: User | FlowInitiator,
    form_snapshot: dict | None = None,
    variables: dict | None = None,
) -> ApprovalInstance:
    """发起审批（业务模块唯一入口之一）。已存在 running 实例 → 70004。

    定义解析：definition_id 优先（OA 表单绑定具体版本行，钉住版本）；
    否则按 code 取最新版本的启用定义（老版本老实例流转，新版本新实例）。

    `initiator` 允许是 `FlowInitiator`（外部发起人，如门户合作方），
    引擎只取 id / name / username 三个属性。
    """
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

    if definition_id:
        definition = db.get(ApprovalDefinition, definition_id)
        if not definition or definition.deleted:
            definition = None
    else:
        definition = db.scalar(
            select(ApprovalDefinition)
            .where(
                ApprovalDefinition.code == definition_code,
                ApprovalDefinition.enabled == 1,
                ApprovalDefinition.deleted == 0,
            )
            .order_by(ApprovalDefinition.flow_version.desc(), ApprovalDefinition.id.desc())
            .limit(1)
        )
    if not definition:
        raise BizException(R.GENERIC_NOT_FOUND, f"流程定义不存在或未启用：{definition_code or definition_id}")
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


def _options_of(db: Session, instance: ApprovalInstance) -> dict:
    """流程通用选项（ApprovalDefinition.options）。

    未配置时返回空 dict —— 所有开关**保持既有行为**（向后兼容，E1 企业微信移植）。
    """
    if not instance.definition_id:
        return {}
    definition = db.get(ApprovalDefinition, instance.definition_id)
    if not definition or not definition.options:
        return {}
    data = parse_json(definition.options, {})
    return data if isinstance(data, dict) else {}


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


def approve(db: Session, task_id: int, user: User, comment: str = "", signature: str = "") -> ApprovalInstance:
    task = _get_open_task(db, task_id, user)
    instance, nodes = _load_running(db, task)
    options = _options_of(db, instance)
    node = _node_config(nodes, task.seq)
    # 流程通用选项：意见必填 / 意见需签名 / 办理意见必填（未配置开关时维持"意见可空"）
    if options.get("commentRequired") and not (comment or "").strip():
        raise BizException(R.APPROVAL_COMMENT_REQUIRED)
    # 意见需签名只作用于**审批**节点（办理节点走「办理意见必填」口径）
    is_executor = bool(node and node.node_type == "executor")
    if not is_executor and options.get("commentSignRequired") and not (signature or "").strip():
        raise BizException(R.APPROVAL_COMMENT_REQUIRED, "审批意见需签名")
    if (
        node
        and node.node_type == "executor"
        and options.get("executorCommentRequired")
        and not (comment or "").strip()
    ):
        raise BizException(R.APPROVAL_COMMENT_REQUIRED, "办理意见必填")
    task.status = "agreed"
    task.comment = comment or ""
    task.acted_at = datetime.now()
    task.acted_by_id = user.id
    _record(
        db,
        instance,
        "agree",
        user,
        comment,
        node_name=task.node_name,
        seq=task.seq,
        payload={"signature": signature} if signature else None,
    )

    sign_mode = node.sign_mode if node else "or"
    if node and node.node_type == "executor":
        sign_mode = "or"  # 办理节点：任一办理人处理即推进
    if node and node.approver_type == "SUPERVISOR_CHAIN":
        sign_mode = "sequential"  # 逐级链条复用 sequential 语义（与 _walk 建待办一致）
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


def reject(db: Session, task_id: int, user: User, comment: str, signature: str = "") -> ApprovalInstance:
    if not (comment or "").strip():
        raise BizException(R.APPROVAL_COMMENT_REQUIRED)
    task = _get_open_task(db, task_id, user)
    instance, nodes = _load_running(db, task)
    options = _options_of(db, instance)
    node = _node_config(nodes, task.seq)
    if not (node and node.node_type == "executor") and options.get("commentSignRequired"):
        if not (signature or "").strip():
            raise BizException(R.APPROVAL_COMMENT_REQUIRED, "审批意见需签名")
    task.status = "rejected"
    task.comment = comment
    task.acted_at = datetime.now()
    task.acted_by_id = user.id
    _record(
        db,
        instance,
        "reject",
        user,
        comment,
        node_name=task.node_name,
        seq=task.seq,
        payload={"signature": signature} if signature else None,
    )
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
    options = _options_of(db, instance)
    # 「通过后申请人可撤销」（企业微信通用选项）：已通过的实例允许发起人撤回
    withdraw_approved = instance.status == "approved" and bool(options.get("allowWithdrawAfterApproved"))
    if instance.status != "running" and not withdraw_approved:
        raise BizException(R.APPROVAL_INVALID_STATE)
    if not withdraw_approved:
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
    if _options_of(db, instance).get("allowAddSign") is False:
        raise BizException(R.GENERIC_PARAM, "该流程未开启加签")
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
