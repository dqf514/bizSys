"""AI 流程路由建议：按业务类型 + 金额/分类 + 组织角色与同类流程，建议审批节点链。

仅返回建议清单（不落库），由管理员在流程定义编辑弹窗中人工采纳后才修改定义；
AI 给出的审批人（USER id / ROLE code）服务端逐一校验存在且启用，非法节点直接丢弃，
全部被丢弃时抛 AI_PARSE_FAILED —— 绝不把未核验的审批人写进流程定义。
"""

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.admin.models import Role
from app.modules.approval.models import ApprovalDefinition
from app.modules.auth.models import User

SUGGEST_PROMPT_VERSION = "v1"
SUGGEST_NODE_LIMIT = 8
_DEF_SAMPLE_LIMIT = 5

ORG_TYPES = ("DEPT_LEADER", "PARENT_DEPT_LEADER", "SUPERVISOR_CHAIN")
APPROVER_TYPES = ("USER", "ROLE") + ORG_TYPES
SIGN_MODES = ("or", "and")

SUGGEST_SYSTEM = (
    "你是企业审批流程设计助手。根据业务类型、金额/分类与组织角色清单，建议一条审批链，输出严格 JSON："
    '{"nodes":[{"nodeName":"节点名","approverType":"USER|ROLE|DEPT_LEADER|PARENT_DEPT_LEADER|SUPERVISOR_CHAIN",'
    '"approverValue":"USER 时为用户ID，ROLE 时为角色code，组织类型可空","signMode":"or|and"}],'
    '"rationale":"设计理由（120字内）"}。规则：1-6 个审批节点；审批人只能从给定的用户/角色清单中选；'
    "金额较大时建议增加高层级节点；组织类型含义：DEPT_LEADER=发起人部门负责人，"
    "PARENT_DEPT_LEADER=上级部门负责人，SUPERVISOR_CHAIN=逐级负责人链。只输出 JSON，不要输出其他内容。"
)


def _enabled_users(db: Session) -> list[dict]:
    rows = db.scalars(
        select(User).where(User.status == "enabled", User.deleted == 0).order_by(User.id).limit(50)
    ).all()
    return [{"id": u.id, "name": u.name or u.username, "deptName": u.dept_name or ""} for u in rows]


def _enabled_roles(db: Session) -> list[dict]:
    rows = db.scalars(
        select(Role).where(Role.status == "enabled", Role.deleted == 0).order_by(Role.id).limit(50)
    ).all()
    return [{"code": r.code, "name": r.name} for r in rows]


def _sample_definitions(db: Session, biz_type: str) -> list[dict]:
    """同 biz_type 现有定义的节点摘要（每 code 最新版本，≤5 条），供 AI 参考既有审批链风格。"""
    rows = db.scalars(
        select(ApprovalDefinition)
        .where(ApprovalDefinition.biz_type == biz_type, ApprovalDefinition.enabled == 1,
               ApprovalDefinition.deleted == 0)
        .order_by(ApprovalDefinition.id)
    ).all()
    latest: dict[str, int] = {}
    for d in rows:
        latest[d.code] = max(latest.get(d.code, 0), d.flow_version)
    out = []
    for d in rows:
        if d.flow_version != latest[d.code]:
            continue
        nodes = [n for n in d.nodes if n.deleted == 0 and n.node_type == "approval"]
        out.append(
            {
                "code": d.code,
                "name": d.name,
                "nodes": [
                    {"nodeName": n.node_name, "approverType": n.approver_type, "signMode": n.sign_mode}
                    for n in nodes
                ],
            }
        )
        if len(out) >= _DEF_SAMPLE_LIMIT:
            break
    return out


def _validate_nodes(db: Session, raw_nodes: list) -> list[dict]:
    """AI 节点 → 服务端校验后的合法节点清单（回填 approverName）。非法节点丢弃。"""
    out: list[dict] = []
    for item in raw_nodes[:SUGGEST_NODE_LIMIT]:
        if not isinstance(item, dict):
            continue
        atype = str(item.get("approverType") or "").strip().upper()
        if atype not in APPROVER_TYPES:
            continue
        value = str(item.get("approverValue") or "").strip()[:64]
        name = ""
        if atype == "USER":
            try:
                uid = int(value)
            except (TypeError, ValueError):
                continue
            u = db.get(User, uid)
            if not u or u.deleted or u.status != "enabled":
                continue
            name = u.name or u.username
            value = str(uid)
        elif atype == "ROLE":
            role = db.scalar(
                select(Role).where(Role.code == value, Role.status == "enabled", Role.deleted == 0)
            )
            if not role:
                continue
            name = role.name
        else:  # 组织类型：approver_value 为可选兜底角色 code，存在才保留
            if value:
                role = db.scalar(
                    select(Role).where(Role.code == value, Role.status == "enabled", Role.deleted == 0)
                )
                if not role:
                    value = ""
        sign = str(item.get("signMode") or "or").strip().lower()
        out.append(
            {
                "nodeName": str(item.get("nodeName") or "").strip()[:64] or "审批节点",
                "approverType": atype,
                "approverValue": value,
                "approverName": name,
                "signMode": sign if sign in SIGN_MODES else "or",
            }
        )
    return out


def parse_suggest_output(db: Session, raw: str) -> dict:
    """AI 输出 → {nodes, rationale}。无法解析/全部节点非法抛 BizException(AI_PARSE_FAILED)。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
    except ValueError as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请稍后再试") from exc
    nodes = _validate_nodes(db, parsed.get("nodes") or [])
    if not nodes:
        raise BizException(R.AI_PARSE_FAILED, "AI 未给出可用审批节点，请稍后再试")
    rationale = str(parsed.get("rationale") or "").strip()[:300]
    return {"nodes": nodes, "rationale": rationale}


def ai_suggest(db: Session, user: User, biz_type: str, name: str = "",
               amount: float | None = None, category: str = "") -> dict:
    """审批链建议入口（admin:flow:edit）。只回建议不落库。"""
    from app.services import ai as ai_svc

    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或流程建议功能已停用")

    ctx = {
        "bizType": biz_type,
        "name": name[:64],
        "amount": amount,
        "category": category[:64],
        "users": _enabled_users(db),
        "roles": _enabled_roles(db),
        "existingDefinitions": _sample_definitions(db, biz_type),
    }
    messages = [
        {"role": "system", "content": SUGGEST_SYSTEM},
        {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db,
            feature="flow_route",
            messages=messages,
            user=user,
            biz_type="approval_definition",
            prompt_version=SUGGEST_PROMPT_VERSION,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    return parse_suggest_output(db, raw)
