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


# ---------------- 二期：招投标 ----------------


class TenderProject(BaseModel):
    """招标项目。状态机：draft → published → evaluating → awarding → awarded；terminated（终止）。

    发布时发放 ZB 编号并对外可见（门户公告）；evaluating 起投标关闭；awarding 为定标审批中。
    """

    __tablename__ = "pur_tender"

    tender_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="招标编号 ZB...（发布时发放，draft 为空）"
    )
    name: Mapped[str] = mapped_column(String(255), index=True, comment="项目名称")
    request_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联采购申请")
    request_no: Mapped[str] = mapped_column(String(32), default="", comment="申请编号冗余")
    tender_method: Mapped[str] = mapped_column(String(16), default="public", comment="字典 tender_method")
    budget_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="预算金额")
    reg_deadline: Mapped[datetime | None] = mapped_column(nullable=True, comment="报名截止时间")
    bid_deadline: Mapped[datetime | None] = mapped_column(nullable=True, comment="投标截止时间")
    open_time: Mapped[datetime | None] = mapped_column(nullable=True, comment="开标时间")
    announcement: Mapped[str | None] = mapped_column(Text, nullable=True, comment="公告内容")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    award_bid_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="定标审批中的投标（awarding）")
    winner_bid_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="中标投标")
    winner_name: Mapped[str] = mapped_column(String(255), default="", comment="中标单位冗余（公示口径）")
    winner_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="中标价（公示口径）")
    contract_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="定标生成的采购合同（幂等）")
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)


class TenderRegistration(BaseModel):
    """合作方报名。状态：pending → approved / rejected（内部审核）。"""

    __tablename__ = "pur_tender_registration"

    tender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pur_tender.id"), index=True)
    partner_user_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="门户账号 partner_user.id")
    company_name: Mapped[str] = mapped_column(String(255), comment="公司名（报名时快照）")
    contact_name: Mapped[str] = mapped_column(String(64), default="")
    contact_phone: Mapped[str] = mapped_column(String(32), default="")
    qualification_path: Mapped[str] = mapped_column(String(255), default="", comment="资质附件存储路径")
    qualification_name: Mapped[str] = mapped_column(String(255), default="", comment="资质附件原始文件名")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    review_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    review_name: Mapped[str] = mapped_column(String(64), default="")
    review_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_comment: Mapped[str] = mapped_column(String(500), default="")


class TenderBid(BaseModel):
    """投标：通过报名审核的合作方在投标截止前提交；截止/评标后只读。

    一合作方一项目一条有效投标（截止前可覆盖重报）；报价仅内部评标与本人可见。
    """

    __tablename__ = "pur_tender_bid"

    tender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pur_tender.id"), index=True)
    partner_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    registration_id: Mapped[int] = mapped_column(BigInteger, default=0, comment="来源报名")
    company_name: Mapped[str] = mapped_column(String(255), default="")
    price: Mapped[float] = mapped_column(Numeric(14, 2), comment="报价")
    proposal_path: Mapped[str] = mapped_column(String(255), default="", comment="方案附件存储路径")
    proposal_name: Mapped[str] = mapped_column(String(255), default="", comment="方案附件原始文件名")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True, comment="投标说明")
    submit_at: Mapped[datetime | None] = mapped_column(nullable=True, comment="最近提交时间")


class TenderEval(BaseModel):
    """评标记录：一评标人对一投标一条（重复提交覆盖）。定标参考用。"""

    __tablename__ = "pur_tender_eval"

    tender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pur_tender.id"), index=True)
    bid_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("pur_tender_bid.id"), index=True)
    evaluator_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="评标人 sys_user.id")
    evaluator_name: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[float] = mapped_column(Numeric(5, 1), comment="评分 0-100")
    comment: Mapped[str] = mapped_column(String(500), default="", comment="评语")
    recommend: Mapped[int] = mapped_column(default=0, comment="推荐中标 0/1")
