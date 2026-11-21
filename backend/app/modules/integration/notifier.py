"""审批待办通知器：订阅 ApprovalTodoCreated，可插拔通道。

- 站内通知（sys_notify）：始终写入，流程中心/工作台可见；
- 企微应用消息：sys_config 企微凭据就绪（wecom.enabled=1 且 corp/agent/secret 齐）
  且用户已绑定 wecom_userid 时才推送；任何失败仅记日志，不阻断审批主事务。

后续短信/邮件等通道按同一事件订阅挂载即可（ADR-0001 适配层）。
"""

import logging

from sqlalchemy.orm import Session

from app.common.events import ApprovalTodoCreated, subscribe, switch_key
from app.modules.admin.models import Notify
from app.modules.auth.models import User
from app.modules.integration.adapters import ADAPTERS
from app.modules.settings import service as settings_svc

logger = logging.getLogger("bizsys.notify")

# 待办通知开关（管理员可在「流程与事件开关」面板关闭）
SWITCH_TODO_NOTIFY = switch_key("ApprovalTodoCreated", "notify.todo")


def _push_wecom(db: Session, event: ApprovalTodoCreated) -> None:
    user = db.get(User, event.assignee_id)
    if not user or not user.wecom_userid:
        return
    if not settings_svc.wecom_ready(db):
        return
    _, corp_id, agent_id, secret = settings_svc.wecom_creds(db)
    base = settings_svc.get_value(db, settings_svc.KEY_WECOM_CALLBACK).rstrip("/")
    try:
        ADAPTERS["wecom"].send_message(
            user.wecom_userid,
            f"新审批待办：{event.title}",
            corp_id=corp_id,
            secret=secret,
            agent_id=agent_id,
            description=f"节点：{event.node_name}",
            url=f"{base}/approval" if base else "",
        )
    except Exception as exc:  # noqa: BLE001 —— 外部通道失败不阻断审批
        logger.warning("wecom todo push failed: assignee=%s err=%s", event.assignee_id, exc)


def _on_todo_created(event: ApprovalTodoCreated) -> None:
    db: Session = event.db
    try:
        db.add(
            Notify(
                user_id=event.assignee_id,
                title=f"新审批待办：{event.title}",
                content=f"节点：{event.node_name}",
                biz_type=event.biz_type,
                biz_id=event.biz_id,
                link="/approval",
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("in-app todo notify failed: %s", exc)
    try:
        _push_wecom(db, event)
    except Exception as exc:  # noqa: BLE001
        logger.warning("wecom todo push failed: %s", exc)


def register_flow_handlers() -> None:
    """F5：通知类订阅由 ``app.modules.approval.wiring.install()`` 显式装配。

    通知是尽力而为的旁路，``critical=False`` —— 外部通道失败不得阻断审批主事务。
    """
    subscribe(ApprovalTodoCreated, _on_todo_created, key=SWITCH_TODO_NOTIFY, critical=False, name="notify.todo")
