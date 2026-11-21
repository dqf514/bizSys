"""流程绑定注册表（F5「全流程驱动」改造）。

把「哪类单据走哪条流程、审批结果如何回写单据状态」从各业务域的散落代码里抽成
一份**声明式注册表**，由通用运行时统一发起与回写。

设计目标（对应企业信息系统的通行做法）：

- **单据即流程入口**：凡是注册在表里的业务单据，都必须先走审批才能进入下一状态，
  而不是先录数据、事后补签；
- **一处配置，全局生效**：流程 code、开关、状态口径集中登记，管理员可在设置页
  一键停用某类单据的审批（降级为人工审核）；
- **副作用可插拔**：领域特有的联动（发结算单、发通知、改甘特）挂在 ``on_approved``
  等回调上，回调失败语义由调用方决定，不影响通用状态回写。

注册表分两类：

- ``managed=True``（通用托管）：状态回写由本模块的运行时完成，业务域不再重复实现；
- ``managed=False``（域内自管）：该单据的状态回写由业务域自己的订阅者完成
  （历史流程，保留既有行为），注册表只负责**清单展示与总开关**。
"""

import importlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import (
    ApprovalCompleted,
    ApprovalRejected,
    ApprovalWithdrawn,
    DocumentStatusChanged,
    FlowStarted,
    load_callable,
    publish,
    subscribe,
)
from app.core import response as R
from app.core.exceptions import BizException

# 通用回写运行时已安装（幂等）
_runtime_installed = False


@dataclass(frozen=True)
class FlowBinding:
    """一类业务单据与审批流程的绑定关系。"""

    biz_type: str  # 与 approval_instance.biz_type 对齐
    label: str  # 中文名（设置页展示）
    model_path: str  # "模块路径:类名"
    definition_code: str = ""  # 流程定义 code；空 = 按 biz_type 解析绑定的定义
    submit_from: tuple[str, ...] = ("draft", "rejected")  # 允许发起审批的单据状态
    approving_status: str = "approving"  # 发起后单据状态
    approved_status: str = "approved"  # 审批通过后单据状态
    rejected_status: str = "rejected"  # 驳回后单据状态
    withdrawn_status: str = "draft"  # 撤回后单据状态
    status_field: str = "status"
    instance_field: str = "flow_instance_id"
    enabled_key: str = ""  # 流程总开关键；空 = 用 flow.<biz_type>.enabled
    managed: bool = True  # True=通用运行时回写；False=业务域自管
    pass_through: bool = False  # 未配置流程定义时是否允许直通
    pass_through_status: str = ""  # 直通时的目标状态；空 = 用 approved_status
    pass_through_hook: str = ""  # 直通时的副作用回调（"模块:函数"，签名 (db, row, initiator)）
    on_approved: str = ""  # 回调 "模块:函数"，签名 (db, row, event)
    on_rejected: str = ""
    on_withdrawn: str = ""
    submit_perm: str = ""  # 发起审批所需权限码（前端提示用，服务端另行强制）
    doc_no_field: str = ""  # 单号字段，用于标题与事件载荷
    note: str = ""


def _enabled_key(biz_type: str) -> str:
    return f"flow.{biz_type}.enabled"


# ---------------------------------------------------------------------------
# 单据 → 流程 清单
# ---------------------------------------------------------------------------
BINDINGS: list[FlowBinding] = [
    # ===== 已接入审批引擎的历史单据（域内自管状态回写） =====
    FlowBinding(
        biz_type="contract",
        label="合同",
        model_path="app.modules.contract.models:Contract",
        definition_code="contract_approve",
        managed=False,
        submit_perm="contract:contract:submit",
        doc_no_field="contract_no",
        note="历史流程：合同域自定义审批处理器",
    ),
    FlowBinding(
        biz_type="task",
        label="任务立项",
        model_path="app.modules.task.models:Task",
        definition_code="",  # 按 biz_type 解析（管理员自建任务立项流程）
        managed=False,
        submit_perm="task:task:submit",
        doc_no_field="task_no",
        note="历史流程：任务域自定义审批处理器",
    ),
    FlowBinding(
        biz_type="report",
        label="检测报告",
        model_path="app.modules.report.models:Report",
        definition_code="report_sign",
        managed=False,
        submit_perm="report:report:submit",
        doc_no_field="report_no",
    ),
    FlowBinding(
        biz_type="sales_quotation",
        label="销售报价",
        model_path="app.modules.sales.models:SalesQuotation",
        definition_code="quote_approve",
        managed=False,
        submit_perm="sales:quotation:submit",
        doc_no_field="quotation_no",
    ),
    FlowBinding(
        biz_type="settlement",
        label="结算单",
        model_path="app.modules.finance.models:Settlement",
        definition_code="",  # 按 biz_type 解析
        managed=False,
        submit_perm="finance:settlement:submit",
        doc_no_field="settlement_no",
    ),
    FlowBinding(
        biz_type="invoice",
        label="发票",
        model_path="app.modules.finance.models:Invoice",
        definition_code="invoice_apply",
        managed=False,
        submit_perm="finance:invoice:submit",
        doc_no_field="invoice_no",
    ),
    FlowBinding(
        biz_type="purchase_request",
        label="采购申请",
        model_path="app.modules.procurement.models:PurchaseRequest",
        definition_code="purchase_request_approve",
        managed=False,
        submit_perm="procurement:request:submit",
        doc_no_field="request_no",
    ),
    FlowBinding(
        biz_type="purchase_contract",
        label="采购合同",
        model_path="app.modules.procurement.models:PurchaseContract",
        definition_code="purchase_contract_approve",
        managed=False,
        submit_perm="procurement:contract:submit",
        doc_no_field="contract_no",
    ),
    FlowBinding(
        biz_type="tender_award",
        label="定标",
        model_path="app.modules.procurement.models:TenderProject",
        definition_code="tender_award_approve",
        managed=False,
        submit_perm="procurement:tender:award",
        doc_no_field="tender_no",
    ),
    FlowBinding(
        biz_type="oa",
        label="OA 申请",
        model_path="app.modules.oa.models:OaInstance",
        definition_code="",
        managed=False,
        submit_perm="oa:apply:submit",
        note="OA 表单按自身绑定的流程版本流转（definition_id 钉版本）",
    ),
    # ===== F5 新接入审批引擎的单据（通用运行时托管） =====
    FlowBinding(
        biz_type="project",
        label="项目立项",
        model_path="app.modules.project.models:Project",
        definition_code="project_approve",
        submit_from=("draft", "rejected"),
        approving_status="approving",
        approved_status="planning",
        rejected_status="rejected",
        withdrawn_status="draft",
        pass_through=True,
        pass_through_status="planning",
        submit_perm="project:submit",
        doc_no_field="project_no",
        note="立项审批通过后进入策划阶段，可参与智能排程",
    ),
    FlowBinding(
        biz_type="timesheet",
        label="工时填报",
        model_path="app.modules.hr.models:HrTimesheet",
        definition_code="timesheet_approve",
        submit_from=("draft", "rejected"),
        approving_status="approving",
        approved_status="approved",
        rejected_status="rejected",
        withdrawn_status="draft",
        pass_through=True,
        pass_through_status="submitted",
        submit_perm="hr:timesheet:submit",
        note="工时须经部门负责人审批后方可计入项目成本",
    ),
    FlowBinding(
        biz_type="asset_disposal",
        label="资产处置",
        model_path="app.modules.asset.models:Disposal",
        definition_code="asset_disposal_approve",
        submit_from=("draft", "rejected"),
        approving_status="approving",
        approved_status="approved",
        rejected_status="rejected",
        withdrawn_status="draft",
        pass_through=True,
        pass_through_status="approved",
        on_approved="app.modules.asset.flow_handlers:on_disposal_approved",
        submit_perm="asset:disposal:submit",
        doc_no_field="disposal_no",
        note="处置单须经财务与分管领导审批后方可核销",
    ),
    FlowBinding(
        biz_type="asset_receipt",
        label="到货验收",
        model_path="app.modules.asset.models:Receipt",
        definition_code="asset_receipt_approve",
        submit_from=("draft", "rejected"),
        approving_status="approving",
        approved_status="accepted",
        rejected_status="rejected",
        withdrawn_status="draft",
        pass_through=True,
        pass_through_status="accepted",
        pass_through_hook="app.modules.asset.flow_handlers:accept_receipt_pass_through",
        on_approved="app.modules.asset.flow_handlers:on_receipt_approved",
        submit_perm="asset:receipt:submit",
        doc_no_field="receipt_no",
        note="验收通过后才生成入库流水",
    ),
    FlowBinding(
        biz_type="payment",
        label="回款单",
        model_path="app.modules.finance.models:Payment",
        definition_code="payment_confirm",
        submit_from=("draft", "rejected"),
        approving_status="approving",
        approved_status="confirmed",
        rejected_status="rejected",
        withdrawn_status="draft",
        pass_through=True,
        pass_through_status="confirmed",
        pass_through_hook="app.modules.finance.flow_handlers:payment_pass_through",
        on_approved="app.modules.finance.flow_handlers:on_payment_approved",
        on_rejected="app.modules.finance.flow_handlers:on_payment_rejected",
        submit_perm="finance:payment:submit",
        note="回款复核：核对收款信息后确认入账，确认后才核销结算单应收",
    ),
    FlowBinding(
        biz_type="report_seal",
        label="报告用章",
        model_path="app.modules.report.models:Report",
        definition_code="report_seal_approve",
        submit_from=("approved",),
        approving_status="sealing",
        approved_status="seal_approved",
        rejected_status="approved",
        withdrawn_status="approved",
        instance_field="seal_flow_instance_id",
        pass_through=True,
        pass_through_status="seal_approved",
        submit_perm="report:seal:apply",
        note="用章申请与实际用章分离：申请 → 审批 → 有权人执行签章",
    ),
]

_bindings: dict[str, FlowBinding] = {b.biz_type: b for b in BINDINGS}


def register(binding: FlowBinding) -> FlowBinding:
    """注册（或覆盖）一条流程绑定。"""
    _bindings[binding.biz_type] = binding
    return binding


def get(biz_type: str) -> FlowBinding | None:
    return _bindings.get(biz_type)


def all_bindings() -> list[FlowBinding]:
    return list(_bindings.values())


def switch_key(biz_type: str) -> str:
    """流程总开关键。"""
    b = _bindings.get(biz_type)
    return (b.enabled_key if b and b.enabled_key else _enabled_key(biz_type))


def flow_enabled(db: Session, biz_type: str) -> bool:
    """流程是否启用（未注册 → 一律启用，保持历史单据行为不变）。"""
    b = _bindings.get(biz_type)
    if b is None:
        return True
    from app.modules.settings import service as settings_svc

    return settings_svc.flag(db, switch_key(biz_type), True)


def model_of(binding: FlowBinding) -> type:
    """按 "模块:类名" 取业务模型。"""
    mod_path, _, cls_name = binding.model_path.partition(":")
    mod = importlib.import_module(mod_path)
    return getattr(mod, cls_name)


def require_manual(db: Session, biz_type: str) -> None:
    """流程启用时禁止走"人工直通"端点。

    业务域里历史上存在的"直接审批 / 直接验收"端点（如资产处置的 approve、
    到货验收的 accept）本质是**绕过流程的后门**。流程启用后必须堵死，
    只能通过提交审批走流程；流程停用（开关关闭）时才恢复人工直通。
    """
    if flow_enabled(db, biz_type):
        b = _bindings.get(biz_type)
        label = b.label if b else biz_type
        raise BizException(R.APPROVAL_INVALID_STATE, f"{label}已启用审批流程，请提交审批后由流程处理")


def _doc_title(row: Any, binding: FlowBinding) -> str:
    if binding.doc_no_field:
        no = getattr(row, binding.doc_no_field, "") or ""
        if no:
            return f"{binding.label} {no}"
    for attr in ("name", "title", "subject"):
        v = getattr(row, attr, "") or ""
        if v:
            return f"{binding.label} {v}"
    return binding.label


def resolve_definition(db: Session, binding: FlowBinding):
    """解析该绑定对应的流程定义（优先 definition_code，其次按 biz_type 绑定）。"""
    from app.modules.approval import service as approval_svc

    if binding.definition_code:
        return approval_svc.latest_enabled_definition(db, binding.definition_code)
    return approval_svc.resolve_definition(db, binding.biz_type)


def submit_flow(
    db: Session,
    biz_type: str,
    biz_id: int,
    *,
    title: str = "",
    initiator: Any,
    variables: dict | None = None,
    form_snapshot: dict | None = None,
    definition_id: int | None = None,
) -> tuple[Any | None, Any]:
    """统一发起审批（F5 入口）。

    步骤：行锁业务行 → 校验状态与开关 → 解析流程定义 → 开实例 → 回写单据状态 →
    发布 FlowStarted / DocumentStatusChanged。

    Returns:
        (审批实例 or None, 业务行)。实例为 None 表示**直通**（未配置流程定义且允许直通）。
    """
    binding = get(biz_type)
    if binding is None:
        raise BizException(R.GENERIC_PARAM, f"未登记的流程类型：{biz_type}")
    if not flow_enabled(db, biz_type):
        raise BizException(R.APPROVAL_FLOW_DISABLED, f"{binding.label}审批流程已停用")

    model = model_of(binding)
    row = db.scalar(select(model).where(model.id == biz_id).with_for_update())
    if row is None or getattr(row, "deleted", 0):
        raise BizException(R.GENERIC_NOT_FOUND, f"{binding.label}不存在")

    current = getattr(row, binding.status_field, "") or ""
    if current not in binding.submit_from:
        raise BizException(
            R.APPROVAL_INVALID_STATE,
            f"{binding.label}当前状态（{current}）不允许提交审批",
        )

    definition = None
    if definition_id:
        from app.modules.approval.models import ApprovalDefinition

        definition = db.get(ApprovalDefinition, definition_id)
        if definition and (definition.deleted or not definition.enabled):
            definition = None
    if definition is None:
        definition = resolve_definition(db, binding)
    if definition is None:
        if not binding.pass_through:
            raise BizException(
                R.GENERIC_NOT_FOUND,
                f"{binding.label}未配置启用的流程定义（{binding.definition_code or binding.biz_type}）",
            )
        # 直通：未绑定流程定义时按"人工审核"口径直接进入下一状态（与任务/结算单同口径）
        target = binding.pass_through_status or binding.approved_status
        setattr(row, binding.status_field, target)
        row.version = (row.version or 0) + 1
        row.update_time = datetime.now()
        if binding.pass_through_hook:
            hook = load_callable(binding.pass_through_hook)
            if hook is not None:
                hook(db, row, initiator)
        publish(
            DocumentStatusChanged(
                biz_type=binding.biz_type,
                biz_id=biz_id,
                doc_label=_doc_title(row, binding),
                from_status=current,
                to_status=target,
                operator_id=getattr(initiator, "id", 0) or 0,
                db=db,
            )
        )
        return None, row

    from app.modules.approval import engine

    instance = engine.start(
        db,
        biz_type=binding.biz_type,
        biz_id=biz_id,
        definition_id=definition.id,
        title=title or _doc_title(row, binding),
        initiator=initiator,
        form_snapshot=form_snapshot,
        variables=variables,
    )

    setattr(row, binding.status_field, binding.approving_status)
    if binding.instance_field:
        setattr(row, binding.instance_field, instance.id)
    row.version = (row.version or 0) + 1
    row.update_time = datetime.now()

    publish(
        FlowStarted(
            biz_type=binding.biz_type,
            biz_id=biz_id,
            instance_id=instance.id,
            title=instance.title or "",
            initiator_id=getattr(initiator, "id", 0) or 0,
            definition_code=instance.definition_code or "",
            db=db,
        )
    )
    publish(
        DocumentStatusChanged(
            biz_type=binding.biz_type,
            biz_id=biz_id,
            doc_label=_doc_title(row, binding),
            from_status=current,
            to_status=binding.approving_status,
            operator_id=getattr(initiator, "id", 0) or 0,
            db=db,
        )
    )
    return instance, row


def apply_result(db: Session, biz_type: str, biz_id: int, result: str, event: Any) -> Any | None:
    """按审批结果回写单据状态（通用运行时使用）。

    result: approved / rejected / withdrawn
    """
    binding = get(biz_type)
    if binding is None or not binding.managed:
        return None
    model = model_of(binding)
    row = db.get(model, biz_id)
    if row is None or getattr(row, "deleted", 0):
        return None
    current = getattr(row, binding.status_field, "") or ""
    if current != binding.approving_status:
        return None  # 已被其他分支处理（如中途撤回）

    target = {
        "approved": binding.approved_status,
        "rejected": binding.rejected_status,
        "withdrawn": binding.withdrawn_status,
    }.get(result)
    if not target:
        return None

    setattr(row, binding.status_field, target)
    if binding.instance_field:
        setattr(row, binding.instance_field, getattr(event, "instance_id", None))
    row.version = (row.version or 0) + 1
    row.update_time = datetime.now()

    hook_path = {
        "approved": binding.on_approved,
        "rejected": binding.on_rejected,
        "withdrawn": binding.on_withdrawn,
    }.get(result, "")
    if hook_path:
        hook = load_callable(hook_path)
        if hook is not None:
            hook(db, row, event)

    # 领域钩子可能改写单据状态（如到货验收：全合格 accepted / 部分合格 partial），
    # 事件以**最终状态**为准，避免订阅方收到中间态。
    final = getattr(row, binding.status_field, "") or target
    publish(
        DocumentStatusChanged(
            biz_type=binding.biz_type,
            biz_id=biz_id,
            doc_label=_doc_title(row, binding),
            from_status=current,
            to_status=final,
            operator_id=getattr(event, "operator_id", 0) or 0,
            db=db,
        )
    )
    return row


# ---------------------------------------------------------------------------
# 通用回写运行时
# ---------------------------------------------------------------------------


def _on_completed(event: ApprovalCompleted) -> None:
    apply_result(event.db, event.biz_type, event.biz_id, "approved", event)


def _on_rejected(event: ApprovalRejected) -> None:
    apply_result(event.db, event.biz_type, event.biz_id, "rejected", event)


def _on_withdrawn(event: ApprovalWithdrawn) -> None:
    apply_result(event.db, event.biz_type, event.biz_id, "withdrawn", event)


def install_runtime() -> None:
    """安装通用回写运行时（幂等）。由 wiring.install() 调用。"""
    global _runtime_installed
    if _runtime_installed:
        return
    subscribe(ApprovalCompleted, _on_completed, name="flow.writeback.completed")
    subscribe(ApprovalRejected, _on_rejected, name="flow.writeback.rejected")
    subscribe(ApprovalWithdrawn, _on_withdrawn, name="flow.writeback.withdrawn")
    _runtime_installed = True


def bindings_out(db: Session) -> list[dict[str, Any]]:
    """流程绑定清单（设置页「流程开关」面板用）。"""
    from app.modules.settings import service as settings_svc

    out = []
    for b in all_bindings():
        definition = resolve_definition(db, b)
        out.append(
            {
                "bizType": b.biz_type,
                "label": b.label,
                "definitionCode": b.definition_code,
                "definitionReady": definition is not None,
                "definitionName": definition.name if definition else "",
                "managed": b.managed,
                "switchKey": switch_key(b.biz_type),
                "enabled": settings_svc.flag(db, switch_key(b.biz_type), True),
                "submitFrom": list(b.submit_from),
                "statuses": {
                    "approving": b.approving_status,
                    "approved": b.approved_status,
                    "rejected": b.rejected_status,
                    "withdrawn": b.withdrawn_status,
                },
                "submitPerm": b.submit_perm,
                "note": b.note,
            }
        )
    return out


def capabilities_out(db: Session) -> list[dict[str, Any]]:
    """流程能力清单（登录用户可读）。

    单据页据此决定展示「提交审批」还是「人工直通」入口：流程开关关闭时，
    单据不进入审批中，直接落到通过态。
    """
    out = []
    for b in all_bindings():
        out.append(
            {
                "bizType": b.biz_type,
                "label": b.label,
                "managed": b.managed,
                "enabled": flow_enabled(db, b.biz_type),
                "definitionReady": resolve_definition(db, b) is not None,
                "submitFrom": list(b.submit_from),
                "statuses": {
                    "approving": b.approving_status,
                    "approved": b.approved_status,
                    "rejected": b.rejected_status,
                    "withdrawn": b.withdrawn_status,
                },
                "submitPerm": b.submit_perm,
            }
        )
    return out
