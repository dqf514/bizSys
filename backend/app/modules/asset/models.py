"""资产与库存模块表：ast_* 前缀。

统一框架（不自建权限/组织/公司表）：
- 部门 → `sys_dept`（`dept_id` + `dept_name` 冗余）
- 公司/供应商 → `crm_customer`（往来单位，`supplier_id` + `supplier_name` 冗余）
- 权限 → `sys_menu`（`module:resource:action`，见 seeds/init_data.py::MENU_TREE）
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel

# ---------------- 仓库与库位 ----------------


class Warehouse(BaseModel):
    """仓库主数据。状态：enabled/disabled。"""

    __tablename__ = "ast_warehouse"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="仓库编码")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="仓库名称")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="归属部门 sys_dept.id")
    dept_name: Mapped[str] = mapped_column(String(128), default="", comment="部门名冗余")
    address: Mapped[str] = mapped_column(String(255), default="", comment="仓库地址")
    manager_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="负责人 sys_user.id")
    manager_name: Mapped[str] = mapped_column(String(64), default="")
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="库位总数（冗余统计）")
    phone: Mapped[str] = mapped_column(String(32), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True)


class Location(BaseModel):
    """库位：归属仓库。占用/在库数量由出入库流水汇总回写。"""

    __tablename__ = "ast_location"

    warehouse_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ast_warehouse.id"), index=True)
    code: Mapped[str] = mapped_column(String(32), index=True, comment="库位编码")
    name: Mapped[str] = mapped_column(String(128), default="", comment="库位名称")
    area: Mapped[str] = mapped_column(String(64), default="", index=True, comment="所在区域")
    capacity: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True, comment="容量")
    used: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="占用容量")
    qty_on_hand: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="在库数量")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True)


# ---------------- 存货档案 ----------------


class Item(BaseModel):
    """存货（物料）档案：在库数量的计算基准，安全库存用于预警。"""

    __tablename__ = "ast_item"

    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="存货编码")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="存货名称")
    spec: Mapped[str] = mapped_column(String(255), default="", comment="规格型号")
    unit: Mapped[str] = mapped_column(String(16), default="", comment="单位")
    category: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 stock_category")
    unit_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="参考单价")
    safety_stock: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="安全库存")
    max_stock: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="库存上限")
    default_warehouse_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    default_location_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    supplier_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="供应公司 crm_customer.id"
    )
    supplier_name: Mapped[str] = mapped_column(String(128), default="", comment="供应公司名冗余")
    manufacturer: Mapped[str] = mapped_column(String(128), default="", comment="生产厂家")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="enabled", index=True)


# ---------------- 采购订单 ----------------


class PurchaseOrder(BaseModel):
    """物资采购订单。状态机：draft → confirmed（已确认）→ closed（已完成/已入库）。"""

    __tablename__ = "ast_purchase_order"

    order_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="订单编号 PO...")
    title: Mapped[str] = mapped_column(String(255), index=True, comment="订单标题")
    supplier_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="供应公司 crm_customer.id")
    supplier_name: Mapped[str] = mapped_column(String(128), default="", comment="供应公司名冗余")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    arrive_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="预计到货日期")
    total_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="订单金额")
    handler_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    handler_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)

    items = relationship(
        "PurchaseOrderItem",
        foreign_keys="PurchaseOrderItem.order_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PurchaseOrderItem(BaseModel):
    __tablename__ = "ast_purchase_order_item"

    order_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ast_purchase_order.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="存货 ast_item.id")
    item_code: Mapped[str] = mapped_column(String(32), default="")
    item_name: Mapped[str] = mapped_column(String(255), comment="存货名称")
    spec: Mapped[str] = mapped_column(String(255), default="")
    unit: Mapped[str] = mapped_column(String(16), default="")
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), comment="数量")
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="单价")
    remark: Mapped[str] = mapped_column(String(500), default="")


# ---------------- 到货验收 ----------------


class Receipt(BaseModel):
    """到货验收单。状态机：draft → accepted（合格）/ partial（部分合格）/ rejected（不合格）。"""

    __tablename__ = "ast_receipt"

    receipt_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="验收单号 YS...")
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="来源采购订单")
    order_no: Mapped[str] = mapped_column(String(32), default="", comment="采购订单号冗余")
    warehouse_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    warehouse_name: Mapped[str] = mapped_column(String(128), default="")
    supplier_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    supplier_name: Mapped[str] = mapped_column(String(128), default="")
    arrive_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="到货数量")
    qualified_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="合格数量")
    inspector_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    inspector_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)

    items = relationship(
        "ReceiptItem",
        foreign_keys="ReceiptItem.receipt_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ReceiptItem(BaseModel):
    __tablename__ = "ast_receipt_item"

    receipt_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ast_receipt.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    item_code: Mapped[str] = mapped_column(String(32), default="")
    item_name: Mapped[str] = mapped_column(String(255), comment="存货名称")
    spec: Mapped[str] = mapped_column(String(255), default="")
    unit: Mapped[str] = mapped_column(String(16), default="")
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="到货数量")
    qualified_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="合格数量")
    location_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="入库库位")
    location_code: Mapped[str] = mapped_column(String(32), default="")
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    remark: Mapped[str] = mapped_column(String(500), default="")


# ---------------- 库存台账 ----------------


class StockLedger(BaseModel):
    """库存流水（台账）。来源：到货验收/盘点调整/领用归还/手工登记；非手工来源只读。"""

    __tablename__ = "ast_ledger"

    direction: Mapped[str] = mapped_column(String(8), index=True, comment="in 入库 / out 出库")
    item_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    item_code: Mapped[str] = mapped_column(String(32), default="")
    item_name: Mapped[str] = mapped_column(String(128), default="")
    unit: Mapped[str] = mapped_column(String(16), default="")
    warehouse_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    warehouse_name: Mapped[str] = mapped_column(String(128), default="")
    location_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    location_code: Mapped[str] = mapped_column(String(32), default="")
    quantity: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="数量（正数）")
    unit_price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="金额")
    reason: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 stock_reason")
    biz_type: Mapped[str] = mapped_column(String(32), default="manual", index=True, comment="业务来源")
    biz_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    biz_no: Mapped[str] = mapped_column(String(32), default="", comment="来源单号")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    happen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True, comment="发生时间")
    remark: Mapped[str] = mapped_column(String(500), default="")


# ---------------- 库存盘点 ----------------


class StockCount(BaseModel):
    """库存盘点单。状态机：draft → counting（盘点中）→ finished（已完成，差异已入账）。"""

    __tablename__ = "ast_count"

    count_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="盘点单号 PD...")
    warehouse_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    warehouse_name: Mapped[str] = mapped_column(String(128), default="")
    count_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="盘点条目数")
    diff_count: Mapped[int] = mapped_column(Integer, default=0, comment="差异条目数")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)

    items = relationship(
        "StockCountItem",
        foreign_keys="StockCountItem.count_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class StockCountItem(BaseModel):
    __tablename__ = "ast_count_item"

    count_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ast_count.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    item_code: Mapped[str] = mapped_column(String(32), default="")
    item_name: Mapped[str] = mapped_column(String(128), default="")
    unit: Mapped[str] = mapped_column(String(16), default="")
    location_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    location_code: Mapped[str] = mapped_column(String(32), default="")
    book_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="账面数量")
    actual_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="实盘数量")
    diff_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="差异数量")
    price: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    diff_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="差异金额")
    reason: Mapped[str] = mapped_column(String(255), default="", comment="差异原因")


# ---------------- 样车样件 ----------------


class Prototype(BaseModel):
    """样车样件台账。状态：in_stock 在库 / loaned 已借出 / maintenance 维修中 / scrapped 已报废。"""

    __tablename__ = "ast_prototype"

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True, comment="样件编号")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="样件名称")
    kind: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 prototype_kind")
    model: Mapped[str] = mapped_column(String(64), default="", comment="型号")
    vin: Mapped[str] = mapped_column(String(64), default="", comment="车架号/识别号")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    location_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    location_name: Mapped[str] = mapped_column(String(128), default="")
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="价值")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="in_stock", index=True)


class PrototypeLoan(BaseModel):
    """样件出借归还。状态机：borrowed → returned（已归还）。"""

    __tablename__ = "ast_prototype_loan"

    loan_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="借出单号 LJ...")
    prototype_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="样件 ast_prototype.id")
    prototype_code: Mapped[str] = mapped_column(String(64), default="")
    prototype_name: Mapped[str] = mapped_column(String(128), default="")
    borrower_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    borrower_name: Mapped[str] = mapped_column(String(64), default="")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    loan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="应归还日期")
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purpose: Mapped[str] = mapped_column(String(500), default="", comment="用途")
    handler_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    handler_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="borrowed", index=True)


# ---------------- 资产与折旧 ----------------


class FixedAsset(BaseModel):
    """固定资产台账（折旧与价值）。状态：in_use 在用 / idle 闲置 / repaired 维修中 / scrapped 已报废。"""

    __tablename__ = "ast_asset"

    asset_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="资产编号 ZC...")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="资产名称")
    category: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 asset_category")
    model: Mapped[str] = mapped_column(String(64), default="", comment="型号")
    spec: Mapped[str] = mapped_column(String(255), default="", comment="规格")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    custodian_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="使用人")
    custodian_name: Mapped[str] = mapped_column(String(64), default="")
    location: Mapped[str] = mapped_column(String(255), default="", comment="存放地点")
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="原值")
    salvage_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0.05, comment="残值率 0-1")
    useful_life_months: Mapped[int] = mapped_column(Integer, default=60, comment="预计使用月数")
    accum_depreciation: Mapped[float] = mapped_column(Numeric(14, 2), default=0, comment="累计折旧")
    net_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="净值")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="in_use", index=True)


class Depreciation(BaseModel):
    """折旧计提记录（按期 YYYY-MM）。"""

    __tablename__ = "ast_depreciation"

    asset_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ast_asset.id"), index=True)
    asset_no: Mapped[str] = mapped_column(String(32), default="")
    asset_name: Mapped[str] = mapped_column(String(128), default="")
    period: Mapped[str] = mapped_column(String(7), index=True, comment="计提期 YYYY-MM")
    amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, comment="本期折旧额")
    accum_amount: Mapped[float] = mapped_column(Numeric(14, 2), default=0, comment="累计折旧额")
    net_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0, comment="计提后净值")
    method: Mapped[str] = mapped_column(String(32), default="straight_line", comment="字典 depreciation_method")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    happen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    remark: Mapped[str] = mapped_column(String(500), default="")


# ---------------- 处置与报废 ----------------


class Disposal(BaseModel):
    """资产处置与报废。状态机：draft → approved（已批准）→ done（已处置）。"""

    __tablename__ = "ast_disposal"

    disposal_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="处置单号 CZ...")
    asset_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="资产 ast_asset.id")
    asset_no: Mapped[str] = mapped_column(String(32), default="")
    asset_name: Mapped[str] = mapped_column(String(128), default="")
    disposal_type: Mapped[str] = mapped_column(String(32), default="scrap", index=True, comment="字典 disposal_type")
    apply_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    original_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="资产原值")
    net_value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="处置前净值")
    disposal_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="处置收入")
    reason: Mapped[str] = mapped_column(String(1000), default="", comment="处置原因")
    handler_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    handler_name: Mapped[str] = mapped_column(String(64), default="")
    approver_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    approver_name: Mapped[str] = mapped_column(String(64), default="")
    approve_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)


# ---------------- 工具与领用 ----------------


class Tool(BaseModel):
    """工具台账。状态：in_stock 在库 / loaned 已借出 / maintenance 维修中 / scrapped 已报废。"""

    __tablename__ = "ast_tool"

    tool_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="工具编号 GJ...")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="工具名称")
    spec: Mapped[str] = mapped_column(String(255), default="", comment="规格")
    model: Mapped[str] = mapped_column(String(64), default="")
    category: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 asset_category")
    unit: Mapped[str] = mapped_column(String(16), default="")
    warehouse_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    warehouse_name: Mapped[str] = mapped_column(String(128), default="")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="价值")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="in_stock", index=True)


class ToolLoan(BaseModel):
    """工具领用归还。状态机：borrowed → returned（已归还）。"""

    __tablename__ = "ast_tool_loan"

    loan_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="领用单号 LY...")
    tool_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="工具 ast_tool.id")
    tool_no: Mapped[str] = mapped_column(String(32), default="")
    tool_name: Mapped[str] = mapped_column(String(128), default="")
    borrower_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    borrower_name: Mapped[str] = mapped_column(String(64), default="")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(128), default="")
    loan_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="应归还日期")
    return_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purpose: Mapped[str] = mapped_column(String(500), default="", comment="用途")
    remark: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(16), default="borrowed", index=True)
