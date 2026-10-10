"""财务 3 表：fin_settlement / fin_invoice / fin_payment。"""

from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class Settlement(BaseModel):
    """结算单：pending 待开票 → invoicing 开票审批中 → invoiced 已开票 → paid 已到账。"""

    __tablename__ = "fin_settlement"
    __table_args__ = (Index("ix_fin_settlement_status_update_time", "status", "update_time"),)

    settlement_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="结算单号 HK...")
    task_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, comment="task_task.id（一任务一结算单）")
    task_no: Mapped[str] = mapped_column(String(32), default="", comment="任务编号冗余")
    contract_no: Mapped[str] = mapped_column(String(32), default="", comment="合同号冗余")
    customer_name: Mapped[str] = mapped_column(String(128), default="", comment="客户名冗余")
    contract_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="ctr_contract.id")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="crm_customer.id")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), comment="结算金额")
    invoiceable_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), comment="可开票金额")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_instance_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="最近一次开票审批实例"
    )


class Invoice(BaseModel):
    """发票：审批通过后生成（status=issued），invoice_no 由财务登记时补录。"""

    __tablename__ = "fin_invoice"

    settlement_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="fin_settlement.id")
    invoice_no: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="发票号（财务后补）")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), comment="开票金额")
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="开票日期")
    status: Mapped[str] = mapped_column(String(16), default="approving", comment="approving/issued")
    approval_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


class Payment(BaseModel):
    """到账登记：财务人工录入（网银/汇票/现金/POS）。"""

    __tablename__ = "fin_payment"
    __table_args__ = (Index("ix_fin_payment_settlement_update_time", "settlement_id", "update_time"),)

    payment_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="到账单号 DZ...")
    settlement_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="fin_settlement.id")
    pay_type: Mapped[str] = mapped_column(String(32), default="", comment="字典 pay_type")
    payer_name: Mapped[str] = mapped_column(String(128), comment="付款方名称")
    payer_account: Mapped[str] = mapped_column(String(64), default="", comment="付款方账号")
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), comment="到账金额")
    bank: Mapped[str] = mapped_column(String(128), default="", comment="付款银行")
    paid_at: Mapped[date] = mapped_column(Date, comment="到账日期")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
