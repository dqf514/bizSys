"""合同表 + 附件表。"""

from datetime import datetime

from sqlalchemy import BigInteger, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class Contract(BaseModel):
    """状态机：draft → approving → approved / rejected / voided；审批中禁编辑。"""

    __tablename__ = "ctr_contract"

    contract_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="合同编号 HT...（提交审批时发放，draft 为空）"
    )
    name: Mapped[str] = mapped_column(String(255), index=True, comment="合同名称")
    customer_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="crm_customer.id")
    customer_name: Mapped[str] = mapped_column(String(128), default="", comment="客户名冗余")
    contract_type: Mapped[str] = mapped_column(String(32), default="", comment="字典 contract_type")
    subject_type: Mapped[str] = mapped_column(String(32), default="", comment="标的类型")
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="合同金额")
    start_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    pay_cycle: Mapped[str] = mapped_column(String(32), default="", comment="字典 pay_cycle")
    delivery: Mapped[str] = mapped_column(String(32), default="", comment="字典 delivery_way")
    seal_type: Mapped[str] = mapped_column(String(32), default="", comment="用印类型")
    handler_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="经办人")
    handler_name: Mapped[str] = mapped_column(String(64), default="")
    framework_no: Mapped[str] = mapped_column(String(64), default="", comment="框架合同号")
    payment_org: Mapped[str] = mapped_column(String(128), default="", comment="付款单位")
    contact_person: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="联系人")
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="联系电话")
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    attachments = relationship(
        "ContractAttachment",
        foreign_keys="ContractAttachment.contract_id",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ContractAttachment(BaseModel):
    __tablename__ = "ctr_contract_attachment"

    contract_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("ctr_contract.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    size: Mapped[int] = mapped_column(BigInteger, default=0)
    content_type: Mapped[str] = mapped_column(String(128), default="")
    path: Mapped[str] = mapped_column(String(255), comment="相对 upload_dir 的路径")
