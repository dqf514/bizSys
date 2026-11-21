"""流程与事件订阅的**显式装配点**（F5）。

历史问题：各业务域在 ``service.py`` 模块级调用 ``subscribe()``，真正生效依赖
``main.py`` 里那些 ``# noqa`` import —— 少一个 import，对应单据就会**永久卡在
approving**，而且不报错、只能靠人肉排查。

F5 起所有订阅集中在这里显式安装：

- :func:`registry.install_runtime` —— 通用流程回写（注册表里 managed=True 的单据）；
- 各业务域的 ``register_flow_handlers()`` —— 域内自管的状态回写与副作用。

装配顺序有意义：通用运行时最后装，保证"域内自定义处理器"先于通用回写执行
（同一单据只会命中其中一条路径，二者按 biz_type 互斥）。
"""

from app.common.events import handler_count

_installed = False


def install() -> None:
    """安装全部流程与事件订阅（幂等）。由 ``app.main`` 在应用启动时调用。"""
    global _installed
    if _installed:
        return

    from app.modules.approval import registry

    # 1) 通用流程回写运行时（注册表托管的单据）
    registry.install_runtime()

    # 2) 各域自管的审批处理器
    from app.modules.contract.service import register_flow_handlers as _contract_handlers
    from app.modules.finance.service import register_flow_handlers as _finance_handlers
    from app.modules.integration.notifier import register_flow_handlers as _notifier_handlers
    from app.modules.oa.service import register_flow_handlers as _oa_handlers
    from app.modules.procurement.service import register_flow_handlers as _procurement_handlers
    from app.modules.project.flow_handlers import register_flow_handlers as _project_handlers
    from app.modules.report.service import register_flow_handlers as _report_handlers
    from app.modules.sales.service import register_flow_handlers as _sales_handlers
    from app.modules.task.service import register_flow_handlers as _task_handlers

    for fn in (
        _contract_handlers,
        _finance_handlers,
        _oa_handlers,
        _procurement_handlers,
        _report_handlers,
        _sales_handlers,
        _task_handlers,
        _notifier_handlers,
        _project_handlers,
    ):
        fn()

    _installed = True


def installed() -> bool:
    """是否已装配（测试用）。"""
    return _installed


def status() -> dict:
    """装配状态（供诊断接口）。"""
    from app.common.events import registered_switches

    return {"installed": _installed, "handlers": handler_count(), "switches": registered_switches()}
