"""财务入参模型。"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field

from app.core.schemas import CamelModel, OptionalDate


class SettlementIn(CamelModel):
    task_id: int
    amount: Decimal = Field(..., gt=0, le=9999999999999999.99)
    invoiceable_amount: Decimal | None = Field(None, gt=0)
    remark: str = Field("", max_length=2000)


class ApplyInvoiceIn(CamelModel):
    comment: str = Field("", max_length=255)


class SendConfirmIn(CamelModel):
    receiver_id: int
    note: str = Field("", max_length=500)


class ConfirmIn(CamelModel):
    action: Literal["confirm", "object"]
    note: str = Field("", max_length=500)


class InvoiceIn(CamelModel):
    invoice_no: str = Field(..., min_length=1, max_length=64)
    amount: Decimal = Field(..., gt=0, le=9999999999999999.99)
    invoice_date: OptionalDate = None


class PaymentIn(CamelModel):
    settlement_id: int
    pay_type: str = Field(..., min_length=1, max_length=32)
    payer_name: str = Field(..., min_length=1, max_length=128)
    payer_account: str = Field("", max_length=64)
    amount: Decimal = Field(..., gt=0, le=9999999999999999.99)
    bank: str = Field("", max_length=128)
    paid_at: date
    remark: str = Field("", max_length=500)
