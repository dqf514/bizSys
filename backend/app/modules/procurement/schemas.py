"""采购入参模型。"""

from pydantic import Field, model_validator

from app.core.schemas import CamelModel, OptionalDate


class RequestItemIn(CamelModel):
    item_name: str = Field(..., min_length=1, max_length=255)
    spec: str = Field("", max_length=255)
    unit: str = Field("", max_length=16)
    quantity: float = Field(..., gt=0, le=9999999999.99)
    estimate_price: float | None = Field(None, gt=0, le=999999999999.99)
    remark: str = Field("", max_length=500)


class PurchaseRequestIn(CamelModel):
    title: str = Field(..., min_length=1, max_length=255)
    task_id: int | None = None
    purchase_method: str = Field("", max_length=32)
    budget_amount: float | None = Field(None, gt=0, le=999999999999.99)
    expect_date: OptionalDate = None
    reason: str = Field("", max_length=2000)
    remark: str = Field("", max_length=2000)
    items: list[RequestItemIn] = Field(default_factory=list)
    version: int | None = None  # 乐观锁校验（可选）


class PurchaseContractIn(CamelModel):
    name: str = Field(..., min_length=1, max_length=255)
    request_id: int | None = None
    supplier_id: int
    amount: float | None = Field(None, gt=0, le=999999999999.99)
    sign_date: OptionalDate = None
    start_date: OptionalDate = None
    end_date: OptionalDate = None
    pay_cycle: str = Field("", max_length=32)
    delivery: str = Field("", max_length=32)
    handler_id: int | None = None
    handler_name: str = Field("", max_length=64)
    remark: str = Field("", max_length=2000)
    version: int | None = None

    @model_validator(mode="after")
    def _date_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class GenerateContractIn(CamelModel):
    """申请生成采购合同：可覆盖合同名/供应商/金额，缺省取申请汇总。"""

    name: str = Field("", max_length=255)
    supplier_id: int
    amount: float | None = Field(None, gt=0, le=999999999999.99)
    pay_cycle: str = Field("", max_length=32)
    delivery: str = Field("", max_length=32)
    remark: str = Field("", max_length=2000)


class StockItemIn(CamelModel):
    item_name: str = Field(..., min_length=1, max_length=255)
    spec: str = Field("", max_length=255)
    unit: str = Field("", max_length=16)
    quantity: float = Field(..., gt=0, le=9999999999.99)
    price: float | None = Field(None, gt=0, le=999999999999.99)
    remark: str = Field("", max_length=500)


class StockOrderIn(CamelModel):
    order_type: str = Field(..., pattern="^(in|out)$")
    contract_id: int | None = None
    warehouse: str = Field("", max_length=32)
    handler_id: int | None = None
    handler_name: str = Field("", max_length=64)
    order_date: OptionalDate = None
    remark: str = Field("", max_length=2000)
    items: list[StockItemIn] = Field(default_factory=list, min_length=1)
    version: int | None = None


class SubmitIn(CamelModel):
    comment: str = Field("", max_length=255)
