"""采购表：申请 + 明细 / 采购合同 / 出入库单 + 明细。"""

from datetime import datetime

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class PurchaseRequest(BaseModel):
    """采购申请。状态机：draft → approving → approved / rejected / voided；审批中禁编辑。"""

    __tablename__ = "pur_request"

    request_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="申请编号 PR...（提交审批时发放，draft 为空）"
    )
    title: Mapped[str] = mapped_column(String(255), index=True, comment="申请标题")
    task_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联任务 tk_task.id")
    task_no: Mapped[str] = mapped_column(String(32), default="", comment="任务编号冗余")
    task_name: Mapped[str] = mapped_column(String(255), default="", comment="任务名称冗余")
    purchase_method: Mapped[str] = mapped_column(String(32), default="", comment="字典 purchase_method")
    budget_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="预算金额")
    expect_date: Mapped[datetime | None] = mapped_column(Date, nullable=True, comment="期望到货日期")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, comment="采购事由")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    items = relationship(
        "PurchaseRequestItem",
        foreign_keys="PurchaseRequestItem.request_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PurchaseRequestItem(BaseModel):
    __tablename__ = "pur_request_item"

    request_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pur_request.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(255), comment="物资名称")
    spec: Mapped[str] = mapped_column(String(255), default="", comment="规格型号")
    unit: Mapped[str] = mapped_column(String(16), default="", comment="单位")
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), comment="数量")
    estimate_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="预估单价")
    remark: Mapped[str] = mapped_column(String(500), default="")


class PurchaseContract(BaseModel):
    """采购合同（会签审批）。状态机同采购申请。"""

    __tablename__ = "pur_contract"

    contract_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="合同编号 CG...（提交审批时发放）"
    )
    name: Mapped[str] = mapped_column(String(255), index=True, comment="合同名称")
    request_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="来源采购申请")
    request_no: Mapped[str] = mapped_column(String(32), default="", comment="申请编号冗余")
    supplier_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="供应商 crm_customer.id")
    supplier_name: Mapped[str] = mapped_column(String(128), default="", comment="供应商名冗余")
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="合同金额")
    sign_date: Mapped[datetime | None] = mapped_column(Date, nullable=True, comment="签订日期")
    start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    pay_cycle: Mapped[str] = mapped_column(String(32), default="", comment="字典 pay_cycle")
    delivery: Mapped[str] = mapped_column(String(32), default="", comment="字典 delivery_way")
    handler_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="经办人")
    handler_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)


class StockOrder(BaseModel):
    """出入库单。状态机：registered → confirmed（确认后只读）；无审批流。"""

    __tablename__ = "pur_stock_order"

    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="单号 RK.../CK...（登记即发放）")
    order_type: Mapped[str] = mapped_column(String(8), index=True, comment="in 入库 / out 出库")
    contract_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联采购合同")
    contract_no: Mapped[str] = mapped_column(String(32), default="", comment="采购合同号冗余")
    contract_name: Mapped[str] = mapped_column(String(255), default="", comment="采购合同名冗余")
    warehouse: Mapped[str] = mapped_column(String(32), default="", comment="字典 warehouse")
    handler_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="经办人")
    handler_name: Mapped[str] = mapped_column(String(64), default="")
    order_date: Mapped[datetime | None] = mapped_column(Date, nullable=True, comment="出入库日期")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="registered", index=True)
    # 二期扩展位：source_type/source_id 接招投标结果/资产台账
    source_type: Mapped[str] = mapped_column(String(32), default="", comment="来源类型（二期预留）")
    source_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="来源单据（二期预留）")

    items = relationship(
        "StockOrderItem",
        foreign_keys="StockOrderItem.order_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class StockOrderItem(BaseModel):
    __tablename__ = "pur_stock_item"

    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pur_stock_order.id"), index=True)
    item_name: Mapped[str] = mapped_column(String(255), comment="物资名称")
    spec: Mapped[str] = mapped_column(String(255), default="", comment="规格型号")
    unit: Mapped[str] = mapped_column(String(16), default="", comment="单位")
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), comment="数量")
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="单价")
    remark: Mapped[str] = mapped_column(String(500), default="")
