"""HR 域的审批事件回调（B9-C3 人员授权）。

授权是**不允许绕过审批**的单据（`pass_through=False`）：未配置启用的流程定义时
提交审批直接报错，不存在"人工直通"后门。
"""

from app.modules.hr import authorization as auth


def _operator_name(db, operator_id: int | None) -> str:
    """事件载荷只有 operator_id，姓名回查一次（写进授权行与变更轨迹）。"""
    if not operator_id:
        return ""
    from app.modules.auth.models import User

    u = db.get(User, operator_id)
    return (u.name or u.username) if u else ""


def on_authorization_approved(db, row, event) -> None:
    """授权审批通过 → confirmed（批准人落库 + 写变更轨迹）。

    通用运行时（`approval/registry.py::apply_result`）已经把状态改成 `confirmed`，
    这里补批准人字段与**只追加**的变更轨迹。
    """
    operator_id = getattr(event, "operator_id", None)
    operator_name = _operator_name(db, operator_id)
    row.approver_id = operator_id
    row.approver_name = operator_name
    row.approved_at = auth._now()
    db.flush()
    auth.write_event(
        db,
        row,
        event_type="approve",
        from_status=auth.STATUS_APPROVING,
        to_status=auth.STATUS_CONFIRMED,
        operator_id=operator_id,
        operator_name=operator_name,
        reason="授权审批通过",
    )


def on_authorization_rejected(db, row, event) -> None:
    """授权审批驳回 → rejected（可修改后重新提交）。"""
    operator_id = getattr(event, "operator_id", None)
    operator_name = _operator_name(db, operator_id)
    db.flush()
    auth.write_event(
        db,
        row,
        event_type="reject",
        from_status=auth.STATUS_APPROVING,
        to_status=auth.STATUS_REJECTED,
        operator_id=operator_id,
        operator_name=operator_name,
        reason=getattr(event, "comment", "") or "授权审批驳回",
    )
