"""销售系统：报价模板 sales_quote_template + 报价单 sales_quotation(+明细/发送留痕)。

- 模板：key+tpl_version 版本化（draft/published/disabled），发布后改版走 tpl_version+1 新草稿（同 oa_form）；
  deleted 入唯一键，软删行写行 id 不阻塞同 key+version 重建；
- 报价单：draft → approving → approved/rejected →（发送留痕）→ sent → accepted/declined；终态 voided。
  编号 BJ… 提交审批时发放（草稿不占号）；金额服务端重算（不信任前端/AI 提交值）；
  模板版式以 layout_snapshot 快照落行，模板后续改版不影响已发报价；
- ai_meta 记录 AI 生成来源与回退原因（source/fallbackReason/model/promptVersion），空=纯手工录入。
"""

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class SalesQuoteTemplate(BaseModel):
    """报价模板：版式由 layout_json 描述（抬头/说明/条款/页脚/明细列），表单式编辑 + 实时预览。"""

    __tablename__ = "sales_quote_template"
    __table_args__ = (
        UniqueConstraint("key", "tpl_version", "deleted", name="uq_sales_quote_tpl_key_version"),
    )

    key: Mapped[str] = mapped_column(String(64), index=True, comment="模板标识")
    name: Mapped[str] = mapped_column(String(128), comment="模板名称")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True, comment="draft/published/disabled")
    tpl_version: Mapped[int] = mapped_column(Integer, default=1, comment="模板版本（BaseModel.version 是乐观锁）")
    layout_json: Mapped[str] = mapped_column(
        Text, nullable=True, comment="版式 JSON：headerHtml/introHtml/termsHtml/footerHtml/validDays/itemColumns"
    )
    sort: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SalesQuotation(BaseModel):
    """报价单主表。状态机见模块 docstring；审批中禁编辑（同合同）。"""

    __tablename__ = "sales_quotation"

    quote_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="报价编号 BJ…（提交审批时发放，draft 为空）"
    )
    title: Mapped[str] = mapped_column(String(255), index=True, comment="报价标题")
    customer_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="crm_customer.id")
    customer_name: Mapped[str] = mapped_column(String(128), default="", comment="客户名冗余")
    contact_name: Mapped[str] = mapped_column(String(64), default="", comment="客户联系人")
    contact_phone: Mapped[str] = mapped_column(String(32), default="", comment="联系人电话")
    contact_email: Mapped[str] = mapped_column(
        String(128), default="", comment="联系人邮箱（邮件发送/auto_send 收件人）"
    )
    template_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="模板 sales_quote_template.id")
    tpl_version: Mapped[int] = mapped_column(Integer, default=1, comment="模板版本快照引用")
    layout_snapshot: Mapped[str] = mapped_column(Text, nullable=True, comment="模板版式快照 JSON（渲染/打印用）")
    requirement: Mapped[str] = mapped_column(Text, nullable=True, comment="客户需求描述（AI 生成输入）")
    intro_html: Mapped[str] = mapped_column(Text, nullable=True, comment="报价说明（AI/模板生成后可编辑）")
    terms_html: Mapped[str] = mapped_column(Text, nullable=True, comment="报价条款")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, comment="合计（明细汇总，服务端重算）")
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=6, comment="税率 %（整单一个税率）")
    currency: Mapped[str] = mapped_column(String(8), default="CNY")
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True, comment="报价有效期")
    status: Mapped[str] = mapped_column(
        String(16), default="draft", index=True,
        comment="draft/approving/approved/rejected/sent/accepted/declined/voided",
    )
    ai_meta: Mapped[str] = mapped_column(Text, nullable=True, comment="AI 生成元信息 JSON（来源/回退原因）")
    auto_send: Mapped[int] = mapped_column(Integer, default=0, comment="审批通过自动发送邮件 0/1（默认关）")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最近发送时间")
    sent_channel: Mapped[str] = mapped_column(String(16), default="", comment="最近发送通道 email/print/download")
    sent_to: Mapped[str] = mapped_column(String(255), default="", comment="最近发送收件人")
    feedback_note: Mapped[str] = mapped_column(String(500), default="", comment="客户反馈备注")
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="审批实例")
    contract_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="转合同 ctr_contract.id（幂等）"
    )

    items = relationship(
        "SalesQuotationItem",
        foreign_keys="SalesQuotationItem.quotation_id",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="SalesQuotationItem.seq",
    )


class SalesQuotationItem(BaseModel):
    """报价明细行：amount = qty × unit_price，服务端重算。"""

    __tablename__ = "sales_quotation_item"

    quotation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sales_quotation.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1, comment="行序")
    name: Mapped[str] = mapped_column(String(255), comment="项目名称")
    spec: Mapped[str] = mapped_column(String(255), default="", comment="规格说明")
    unit: Mapped[str] = mapped_column(String(16), default="", comment="单位")
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 2), comment="数量")
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), comment="单价")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), comment="金额（=qty×unit_price，服务端重算）")
    remark: Mapped[str] = mapped_column(String(255), default="")


class SalesQuoteSendLog(BaseModel):
    """报价发送留痕：手动发送与 auto_send 都落行；result=real/debug/marked/skipped/failed。"""

    __tablename__ = "sales_quote_send_log"

    quotation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("sales_quotation.id"), index=True)
    channel: Mapped[str] = mapped_column(String(16), comment="email/print/download")
    recipient: Mapped[str] = mapped_column(String(255), default="", comment="收件人（邮箱或说明）")
    result: Mapped[str] = mapped_column(String(16), comment="real/debug/marked/skipped/failed")
    detail: Mapped[str] = mapped_column(String(500), default="", comment="结果说明/错误信息")
    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="操作人（auto_send 为空）")
    sender_name: Mapped[str] = mapped_column(String(64), default="")
