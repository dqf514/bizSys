"""流程与事件开关（F5「全流程驱动」）。

管理员在这里做两件事：

1. **流程开关** —— 逐类单据启停审批（``flow.<biz_type>.enabled``）。
   关闭后该类单据不能再提交审批（接口返回 70006），用于紧急止血或试点新流程；
2. **事件触发开关** —— 逐条联动启停（``event.trigger.<事件>.<处理器>``）。
   关闭后该联动不再执行（例如"任务开始执行时自动推进项目状态"）。

开关全部落在 ``sys_config``，改动即时生效（写入即失效缓存）。
"""

from sqlalchemy.orm import Session

from app.common.events import EVENT_CATALOG, registered_switches
from app.modules.approval import registry
from app.modules.settings import service as svc


def automation_out(db: Session) -> dict:
    """流程与事件开关面板数据。"""
    flows = registry.bindings_out(db)

    by_event: dict[str, list[dict]] = {}
    for item in registered_switches():
        by_event.setdefault(item["event"], []).append(item)

    events = []
    for name, meta in EVENT_CATALOG.items():
        items = by_event.get(name, [])
        events.append(
            {
                "event": name,
                "label": meta["label"],
                "description": meta["description"],
                "switches": [
                    {
                        "key": i["key"],
                        "name": i["name"],
                        "critical": i["critical"],
                        "enabled": svc.flag(db, i["key"], True),
                    }
                    for i in items
                ],
            }
        )
    return {"flows": flows, "events": events}


def update_automation(db: Session, body, user_id: int) -> dict:
    """保存开关。flows 传 bizType+enabled，events 传 key+enabled。"""
    for item in body.flows or []:
        binding = registry.get(item.biz_type)
        if binding is None:
            continue
        svc.set_value(
            db,
            registry.switch_key(item.biz_type),
            "1" if item.enabled else "0",
            user_id,
            f"{binding.label}审批流程开关",
        )
    for item in body.events or []:
        if not item.key:
            continue
        svc.set_value(
            db,
            item.key,
            "1" if item.enabled else "0",
            user_id,
            "事件触发开关",
        )
    return automation_out(db)
