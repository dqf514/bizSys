"""合同入参模型。"""

from pydantic import Field, model_validator

from app.core.schemas import CamelModel, OptionalDate


class ContractIn(CamelModel):
    name: str = Field(..., min_length=1, max_length=255)
    customer_id: int
    contract_type: str = Field("", max_length=32)
    subject_type: str = Field("", max_length=32)
    # Numeric(14,2)：与结算/到账口径一致的正数上限
    amount: float | None = Field(None, gt=0, le=999999999999.99)
    start_date: OptionalDate = None
    end_date: OptionalDate = None
    pay_cycle: str = Field("", max_length=32)
    delivery: str = Field("", max_length=32)
    seal_type: str = Field("", max_length=32)
    handler_id: int | None = None
    handler_name: str = Field("", max_length=64)
    framework_no: str = Field("", max_length=64)
    payment_org: str = Field("", max_length=128)
    contact_person: str = Field("", max_length=64)
    contact_phone: str = Field("", max_length=32)
    remark: str = Field("", max_length=2000)
    version: int | None = None  # 乐观锁校验（可选）

    @model_validator(mode="after")
    def _date_range(self):
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("结束日期不能早于开始日期")
        return self


class SubmitIn(CamelModel):
    comment: str = Field("", max_length=255)
