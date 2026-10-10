"""合同入参模型。"""

from datetime import date

from pydantic import Field

from app.core.schemas import CamelModel


class ContractIn(CamelModel):
    name: str = Field(..., min_length=1, max_length=255)
    customer_id: int
    contract_type: str = Field("", max_length=32)
    subject_type: str = Field("", max_length=32)
    amount: float | None = None
    start_date: date | None = None
    end_date: date | None = None
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


class SubmitIn(CamelModel):
    comment: str = Field("", max_length=255)
