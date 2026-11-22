"""访客域的审批流程联动（F6：访客预约接入通用审批引擎）。

门户合作方在门户提交访客预约 → `approval/registry.py::submit_flow` 开流程实例 →
审批人（被访人 / 安保，节点可在「流程设置」按表单变量动态指定）在审批中心处理 →
本模块的回调把结果回写到访客单：

- **通过**：置 `approved` → 下发通行凭证 → 通知被访人 → 短信告知访客；
- **驳回**：置 `rejected` → 记录审批意见 → 短信告知访客；
- **直通**（未配置流程定义）：等价于通过，直接下发凭证。

回写后仍会写一行 `vis_approval` 镜像记录，让访客详情页的审批历史保持原有口径。
"""

from sqlalchemy.orm import Session

from app.modules.auth.models import User
from app.modules.visitor import service as svc
from app.modules.visitor.models import VisitorApproval, VisitorVisit

# 镜像记录的审批层级标识（区别于历史域内链的 host/dept/zone）
FLOW_LEVEL = "flow"


def _operator_name(db: Session, event) -> str:
    """取审批人姓名（事件只带 operator_id）。"""
    operator_id = getattr(event, "operator_id", 0) or 0
    if not operator_id:
        return "系统"
    user = db.get(User, operator_id)
    if not user:
        return "系统"
    return user.name or user.username


def _write_mirror(
    db: Session,
    visit: VisitorVisit,
    action: str,
    approver_id: int | None,
    approver_name: str,
    comment: str,
) -> None:
    """写一行审批镜像记录（保持访客详情的审批历史 UI 不变）。"""
    db.add(
        VisitorApproval(
            visit_id=visit.id,
            level=FLOW_LEVEL,
            approver_id=approver_id,
            approver_name=approver_name,
            action=action,
            comment=comment,
        )
    )
    db.flush()


def _notify_visitor_sms(db: Session, visit: VisitorVisit, text: str) -> None:
    """短信提醒访客（尽力而为，通道未配置时静默跳过）。"""
    from app.modules.settings.notify import send_sms_text

    if not visit.phone:
        return
    send_sms_text(db, visit.phone, text)


def _ensure_credential(db: Session, visit: VisitorVisit) -> None:
    """确保访客单有有效通行凭证（幂等）。"""
    if visit.credential_id:
        return
    svc.issue_credential(db, visit)


def on_visit_approved(db: Session, visit: VisitorVisit, event) -> None:
    """审批通过：下发凭证 + 通知被访人 + 短信告知访客。"""
    approver = _operator_name(db, event)
    approver_id = getattr(event, "operator_id", 0) or None
    visit.approved_levels = FLOW_LEVEL
    _write_mirror(db, visit, "approve", approver_id, approver, "审批通过")
    _ensure_credential(db, visit)
    svc.notify_host(db, visit, f"访客申请 {visit.visit_no} 已审批通过，凭证 {visit.credential_no} 已下发")
    svc.notify_security(db, f"访客审批通过：{visit.visit_no}", f"访客 {visit.visitor_name} 已获批，请关注到访", visit)
    _notify_visitor_sms(
        db,
        visit,
        f"【{visit.visit_no}】您的来访申请已审批通过，请按预约时间到访并出示通行凭证。",
    )


def on_visit_rejected(db: Session, visit: VisitorVisit, event) -> None:
    """审批驳回：记录意见 + 短信告知访客。"""
    approver = _operator_name(db, event)
    approver_id = getattr(event, "operator_id", 0) or None
    comment = getattr(event, "comment", "") or "审批未通过"
    _write_mirror(db, visit, "reject", approver_id, approver, comment)
    visit.remark = (visit.remark + "\n" if visit.remark else "") + f"[驳回] {comment}"
    svc.notify_host(db, visit, f"访客申请 {visit.visit_no} 被驳回：{comment}")
    _notify_visitor_sms(db, visit, f"【{visit.visit_no}】您的来访申请未通过：{comment}")


def on_visit_pass_through(db: Session, visit: VisitorVisit, initiator=None) -> None:
    """未配置流程定义时的直通：等价于通过（人工审核口径）。"""
    visit.approved_levels = FLOW_LEVEL
    _ensure_credential(db, visit)
    svc.notify_host(db, visit, f"访客申请 {visit.visit_no} 已受理，凭证 {visit.credential_no} 已下发")
