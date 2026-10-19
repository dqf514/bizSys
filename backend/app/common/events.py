"""进程内同步事件总线（与业务写入同事务；Outbox 留二期，见 ADR-0002）。"""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger("bizsys.events")

_handlers: dict[type, list[Callable]] = defaultdict(list)


def subscribe(event_type: type, handler: Callable) -> None:
    _handlers[event_type].append(handler)


def publish(event: Any) -> None:
    for handler in _handlers.get(type(event), []):
        try:
            handler(event)
        except Exception:
            # 事件处理失败不能吞掉业务事务语义：向上抛由调用方决定回滚
            logger.exception("event handler failed: %s", type(event).__name__)
            raise


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
