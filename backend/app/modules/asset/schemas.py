"""资产与库存入参模型。"""

from pydantic import Field, model_validator

from app.core.schemas import CamelModel, OptionalDate

# ---------------- 仓库与库位 ----------------


class WarehouseIn(CamelModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)
    dept_id: int | None = None
    address: str = Field("", max_length=255)
    manager_id: int | None = None
    manager_name: str = Field("", max_length=64)
    capacity: int | None = Field(None, ge=0, le=100000)
    phone: str = Field("", max_length=32)
    remark: str = Field("", max_length=500)
    status: str = Field("enabled", pattern="^(enabled|disabled)$")
    version: int | None = None


class LocationIn(CamelModel):
    warehouse_id: int
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field("", max_length=128)
    area: str = Field("", max_length=64)
    capacity: float | None = Field(None, ge=0, le=9999999999.99)
    remark: str = Field("", max_length=500)
    status: str = Field("enabled", pattern="^(enabled|disabled)$")
    version: int | None = None


# ---------------- 存货档案 ----------------


class ItemIn(CamelModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)
    spec: str = Field("", max_length=255)
    unit: str = Field("", max_length=16)
    category: str = Field("", max_length=32)
    unit_price: float | None = Field(None, ge=0, le=999999999999.99)
    safety_stock: float = Field(0, ge=0, le=9999999999.99)
    max_stock: float = Field(0, ge=0, le=9999999999.99)
    default_warehouse_id: int | None = None
    default_location_id: int | None = None
    supplier_id: int | None = None
    manufacturer: str = Field("", max_length=128)
    dept_id: int | None = None
    stagnant_days: int = Field(90, ge=0, le=3650)
    remark: str = Field("", max_length=500)
    status: str = Field("enabled", pattern="^(enabled|disabled)$")
    version: int | None = None


# ---------------- BOM（物料清单） ----------------


class BomLineIn(CamelModel):
    item_id: int | None = None
    item_code: str = Field("", max_length=32)
    item_name: str = Field(..., min_length=1, max_length=128)
    spec: str = Field("", max_length=255)
    unit: str = Field("", max_length=16)
    qty: float = Field(1, gt=0, le=9999999999.99)
    loss_rate: float = Field(0, ge=0, le=100)
    ref_designator: str = Field("", max_length=128)
    position: str = Field("", max_length=64)
    remark: str = Field("", max_length=500)


class BomIn(CamelModel):
    parent_item_id: int
    bom_version: str = Field("V1.0", min_length=1, max_length=32)
    effective_date: OptionalDate = None
    remark: str = Field("", max_length=2000)
    lines: list[BomLineIn] = Field(default_factory=list, min_length=1)
    version: int | None = None


# ---------------- 采购订单 ----------------


class PurchaseOrderItemIn(CamelModel):
    item_id: int | None = None
    item_code: str = Field("", max_length=32)
    item_name: str = Field(..., min_length=1, max_length=255)
    spec: str = Field("", max_length=255)
    unit: str = Field("", max_length=16)
    quantity: float = Field(..., gt=0, le=9999999999.99)
    price: float | None = Field(None, ge=0, le=999999999999.99)
    remark: str = Field("", max_length=500)


class PurchaseOrderIn(CamelModel):
    title: str = Field(..., min_length=1, max_length=255)
    supplier_id: int
    dept_id: int | None = None
    order_date: OptionalDate = None
    arrive_date: OptionalDate = None
    total_amount: float | None = Field(None, ge=0, le=999999999999.99)
    handler_id: int | None = None
    handler_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=2000)
    items: list[PurchaseOrderItemIn] = Field(default_factory=list, min_length=1)
    version: int | None = None


# ---------------- 到货验收 ----------------


class ReceiptItemIn(CamelModel):
    item_id: int | None = None
    item_code: str = Field("", max_length=32)
    item_name: str = Field(..., min_length=1, max_length=255)
    spec: str = Field("", max_length=255)
    unit: str = Field("", max_length=16)
    quantity: float = Field(..., ge=0, le=9999999999.99)
    qualified_qty: float = Field(..., ge=0, le=9999999999.99)
    location_id: int | None = None
    price: float | None = Field(None, ge=0, le=999999999999.99)
    remark: str = Field("", max_length=500)


class ReceiptIn(CamelModel):
    order_id: int | None = None
    warehouse_id: int | None = None
    supplier_id: int | None = None
    arrive_date: OptionalDate = None
    inspector_id: int | None = None
    inspector_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=2000)
    items: list[ReceiptItemIn] = Field(default_factory=list, min_length=1)
    version: int | None = None

    @model_validator(mode="after")
    def _qualified_not_over(self):
        for i in self.items:
            if i.qualified_qty > i.quantity:
                raise ValueError("合格数量不能大于到货数量")
        return self


# ---------------- 库存台账 ----------------


class LedgerIn(CamelModel):
    direction: str = Field(..., pattern="^(in|out)$")
    item_id: int
    warehouse_id: int | None = None
    location_id: int | None = None
    quantity: float = Field(..., gt=0, le=9999999999.99)
    unit_price: float | None = Field(None, ge=0, le=999999999999.99)
    reason: str = Field("manual", max_length=32)
    dept_id: int | None = None
    happen_at: OptionalDate = None
    remark: str = Field("", max_length=500)
    version: int | None = None


# ---------------- 库存盘点 ----------------


class StockCountItemIn(CamelModel):
    item_id: int | None = None
    item_code: str = Field("", max_length=32)
    item_name: str = Field(..., min_length=1, max_length=128)
    unit: str = Field("", max_length=16)
    location_id: int | None = None
    book_qty: float = Field(0, ge=0, le=9999999999.99)
    actual_qty: float = Field(0, ge=0, le=9999999999.99)
    reason: str = Field("", max_length=255)


class StockCountIn(CamelModel):
    warehouse_id: int | None = None
    count_date: OptionalDate = None
    operator_id: int | None = None
    operator_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=2000)
    items: list[StockCountItemIn] = Field(default_factory=list, min_length=1)
    version: int | None = None


# ---------------- 样车样件 ----------------


class PrototypeIn(CamelModel):
    code: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    kind: str = Field("", max_length=32)
    model: str = Field("", max_length=64)
    vin: str = Field("", max_length=64)
    dept_id: int | None = None
    location_id: int | None = None
    purchase_date: OptionalDate = None
    value: float | None = Field(None, ge=0, le=999999999999.99)
    remark: str = Field("", max_length=500)
    status: str = Field("in_stock", pattern="^(in_stock|loaned|maintenance|scrapped)$")
    version: int | None = None


class PrototypeLoanIn(CamelModel):
    prototype_id: int
    borrower_id: int | None = None
    borrower_name: str = Field("", max_length=64)
    dept_id: int | None = None
    loan_date: OptionalDate = None
    due_date: OptionalDate = None
    purpose: str = Field("", max_length=500)
    handler_id: int | None = None
    handler_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=500)
    version: int | None = None


class LoanReturnIn(CamelModel):
    return_date: OptionalDate = None
    remark: str = Field("", max_length=500)


# ---------------- 资产与折旧 ----------------


class FixedAssetIn(CamelModel):
    asset_no: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)
    category: str = Field("", max_length=32)
    model: str = Field("", max_length=64)
    spec: str = Field("", max_length=255)
    dept_id: int | None = None
    custodian_id: int | None = None
    custodian_name: str = Field("", max_length=64)
    location: str = Field("", max_length=255)
    purchase_date: OptionalDate = None
    original_value: float | None = Field(None, ge=0, le=999999999999.99)
    salvage_rate: float = Field(0.05, ge=0, le=1)
    useful_life_months: int = Field(60, ge=1, le=1200)
    remark: str = Field("", max_length=500)
    status: str = Field("in_use", pattern="^(in_use|idle|repaired|scrapped)$")
    version: int | None = None


class DepreciateIn(CamelModel):
    period: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    method: str = Field("straight_line", pattern="^(straight_line|double_declining|sum_of_years)$")
    remark: str = Field("", max_length=500)


class DepreciationIn(CamelModel):
    asset_id: int
    period: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: float = Field(..., ge=0, le=999999999999.99)
    method: str = Field("straight_line", pattern="^(straight_line|double_declining|sum_of_years)$")
    remark: str = Field("", max_length=500)
    version: int | None = None


# ---------------- 处置与报废 ----------------


class DisposalIn(CamelModel):
    asset_id: int
    disposal_type: str = Field("scrap", pattern="^(scrap|sell|donate|transfer)$")
    apply_date: OptionalDate = None
    disposal_amount: float | None = Field(None, ge=0, le=999999999999.99)
    reason: str = Field("", max_length=1000)
    handler_id: int | None = None
    handler_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=500)
    version: int | None = None


# ---------------- 工具与领用 ----------------


class ToolIn(CamelModel):
    tool_no: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=128)
    spec: str = Field("", max_length=255)
    model: str = Field("", max_length=64)
    category: str = Field("", max_length=32)
    unit: str = Field("", max_length=16)
    warehouse_id: int | None = None
    dept_id: int | None = None
    purchase_date: OptionalDate = None
    value: float | None = Field(None, ge=0, le=999999999999.99)
    remark: str = Field("", max_length=500)
    status: str = Field("in_stock", pattern="^(in_stock|loaned|maintenance|scrapped)$")
    version: int | None = None


class ToolLoanIn(CamelModel):
    tool_id: int
    borrower_id: int | None = None
    borrower_name: str = Field("", max_length=64)
    dept_id: int | None = None
    loan_date: OptionalDate = None
    due_date: OptionalDate = None
    purpose: str = Field("", max_length=500)
    remark: str = Field("", max_length=500)
    version: int | None = None
