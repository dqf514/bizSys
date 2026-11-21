"""进程内同步事件总线（与业务写入同事务；Outbox 留二期，见 ADR-0002）。

F5「全流程驱动」改造要点：

- **订阅可开关**：每个处理器可挂一个 ``sys_config`` 开关键（``event.trigger.<事件>.<处理器>``），
  管理员可在「流程与事件开关」面板里单独关掉某个联动（如"任务完成后自动生成结算单"），
  不改代码即可降级为人工处理。
- **失败语义分级**：``critical=True``（默认）—— 处理器异常向上抛，业务事务回滚，
  适合"状态回写"这类必须成功的联动；``critical=False`` —— 处理器异常只记日志不阻断，
  适合通知 / 埋点这类尽力而为的联动。
- **目录化**：``EVENT_CATALOG`` 描述每个事件的中文名与用途，``registered_switches()``
  汇总已注册处理器的开关，供设置接口渲染「流程与事件开关」面板。
- **显式装配**：处理器注册由 ``app/modules/approval/wiring.py::install()`` 统一调用，
  不再依赖模块 import 副作用（漏一个 import 就会让单据卡在 approving）。
"""

import importlib
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger("bizsys.events")


@dataclass
class Handler:
    """一条事件订阅。"""

    fn: Callable
    key: str = ""  # sys_config 开关键；空 = 总是执行
    critical: bool = True  # True: 异常上抛回滚业务事务；False: 只记日志
    name: str = ""


_handlers: dict[type, list[Handler]] = defaultdict(list)

# 事件处理器开关键前缀：event.trigger.<事件名>.<处理器名>
SWITCH_PREFIX = "event.trigger."


def switch_key(event_name: str, handler_name: str) -> str:
    """事件处理器开关键（sys_config）。管理员在「流程与事件开关」面板里逐项启停。"""
    return f"{SWITCH_PREFIX}{event_name}.{handler_name}"


def subscribe(
    event_type: type,
    handler: Callable,
    *,
    key: str = "",
    critical: bool = True,
    name: str = "",
) -> None:
    """注册事件处理器。

    Args:
        event_type: 事件类（**精确类型匹配**，不按继承层次派发）。
        handler: 处理函数，入参为事件实例。
        key: 该处理器的开关键（sys_config）；开关闭 → 处理器被跳过。
        critical: 处理器异常是否上抛（默认上抛，保持历史语义）。
        name: 处理器显示名（默认取函数名），用于设置面板与日志。
    """
    _handlers[event_type].append(
        Handler(fn=handler, key=key, critical=critical, name=name or getattr(handler, "__name__", "handler"))
    )


def unsubscribe(event_type: type, handler: Callable) -> None:
    """注销某个处理器（测试用）。"""
    _handlers[event_type] = [h for h in _handlers.get(event_type, []) if h.fn is not handler]


def handler_count() -> int:
    return sum(len(v) for v in _handlers.values())


def _switch_on(db: Any, key: str) -> bool:
    """读 sys_config 开关；读不到（无 db / 无配置）时默认开启。"""
    if db is None:
        return True
    try:
        from app.modules.settings import service as settings_svc

        return settings_svc.flag(db, key, True)
    except Exception:  # noqa: BLE001 — 开关读取失败不得阻断业务
        logger.exception("读取事件开关失败，按开启处理: %s", key)
        return True


def publish(event: Any) -> None:
    """发布事件（同一事务内同步派发，精确类型匹配）。"""
    db = getattr(event, "db", None)
    for h in list(_handlers.get(type(event), [])):
        if h.key and not _switch_on(db, h.key):
            logger.info("event handler skipped (switch off): %s / %s", type(event).__name__, h.name)
            continue
        try:
            h.fn(event)
        except Exception:
            logger.exception("event handler failed: %s / %s", type(event).__name__, h.name)
            if h.critical:
                # 事件处理失败不能吞掉业务事务语义：向上抛由调用方决定回滚
                raise


def registered_switches() -> list[dict[str, Any]]:
    """已注册处理器的开关清单（供「流程与事件开关」面板渲染）。"""
    out: list[dict[str, Any]] = []
    for event_type, hs in _handlers.items():
        for h in hs:
            if not h.key:
                continue
            out.append(
                {
                    "event": event_type.__name__,
                    "eventLabel": EVENT_CATALOG.get(event_type.__name__, {}).get("label", event_type.__name__),
                    "key": h.key,
                    "name": h.name,
                    "critical": h.critical,
                }
            )
    return out


@dataclass
class ApprovalCompleted:
    """审批全部通过。db=发布方会话（处理器复用可保证同事务）。"""

    biz_type: str
    biz_id: int
    instance_id: int
    operator_id: int
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class ApprovalRejected:
    """审批被驳回。"""

    biz_type: str
    biz_id: int
    instance_id: int
    operator_id: int
    comment: str = ""
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class ApprovalWithdrawn:
    """审批被发起人撤回（业务方应把单据回写为可编辑状态）。"""

    biz_type: str
    biz_id: int
    instance_id: int
    operator_id: int
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class ApprovalTodoCreated:
    """新审批待办产生（引擎每次创建 pending 任务时发布，含加签/转办/依次签后继）。

    订阅方典型用途：站内通知、企微/短信等外部通道推送（可插拔通知器）。
    处理器必须自行兜底异常，不得阻断审批主事务。
    """

    biz_type: str
    biz_id: int
    instance_id: int
    title: str
    node_name: str
    assignee_id: int
    assignee_name: str
    operator_id: int
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class TaskAssigned:
    """任务已分配（触发站内提醒 / 企微占位）。"""

    task_id: int
    task_no: str
    dept_id: int | None = None
    operator_id: int = 0
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class FlowStarted:
    """流程实例已发起（F5）。

    订阅方典型用途：把"单据已进入审批"广播给工作台 / 消息中心 / 企微，
    让审批中单据在业务侧可见，而不是只躺在审批模块里。
    """

    biz_type: str
    biz_id: int
    instance_id: int
    title: str
    initiator_id: int
    definition_code: str = ""
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class DocumentStatusChanged:
    """业务单据状态发生变化（F5）。

    系统性的"数据流转"信号：任何域的单据状态迁移都可以发布它，
    由订阅方做二次联动（如任务完成 → 生成结算单、报告签章 → 任务项可开票）。
    """

    biz_type: str
    biz_id: int
    doc_label: str = ""
    from_status: str = ""
    to_status: str = ""
    operator_id: int = 0
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class SchedulePlanPublished:
    """排程方案已发布（F5）。

    订阅方典型用途：同步项目甘特、回写任务计划日期、通知相关人。
    """

    plan_id: int
    plan_no: str
    plan_name: str = ""
    schedule_count: int = 0
    conflict_count: int = 0
    operator_id: int = 0
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


@dataclass
class TaskCompleted:
    """任务已完成（F5）：驱动下游单据自动生成。"""

    task_id: int
    task_no: str = ""
    task_name: str = ""
    operator_id: int = 0
    at: datetime = field(default_factory=datetime.now)
    db: Any = field(default=None, repr=False, compare=False)


# 事件目录：中文名 + 用途说明，供设置面板与文档使用
EVENT_CATALOG: dict[str, dict[str, str]] = {
    "ApprovalCompleted": {"label": "审批通过", "description": "流程全部节点通过后触发：回写单据状态并执行后续联动"},
    "ApprovalRejected": {"label": "审批驳回", "description": "流程被驳回后触发：单据回到可修改状态"},
    "ApprovalWithdrawn": {"label": "审批撤回", "description": "发起人撤回流程后触发：单据回到可编辑状态"},
    "ApprovalTodoCreated": {"label": "审批待办产生", "description": "生成待办时触发：站内信 / 企微 / 短信推送"},
    "TaskAssigned": {"label": "任务分配", "description": "任务分配到人时触发：提醒被指派人"},
    "FlowStarted": {"label": "流程发起", "description": "业务单据提交审批时触发：广播「进入审批」状态"},
    "DocumentStatusChanged": {"label": "单据状态变更", "description": "任意业务单据状态迁移时触发：跨域数据流转"},
    "SchedulePlanPublished": {"label": "排程方案发布", "description": "排程方案发布时触发：同步甘特与任务计划日期"},
    "TaskCompleted": {"label": "任务完成", "description": "任务置为完成时触发：自动生成结算单等下游单据"},
}


def load_callable(path: str) -> Callable | None:
    """按 "module.path:func" 解析可调用对象；解析失败返回 None（不抛）。"""
    if not path or ":" not in path:
        return None
    mod_path, _, func_name = path.partition(":")
    try:
        mod = importlib.import_module(mod_path)
        return getattr(mod, func_name, None)
    except Exception:  # noqa: BLE001
        logger.exception("解析回调失败: %s", path)
        return None
