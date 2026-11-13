"""销售系统：AI 报价（sales_quote_template / sales_quotation / sales_quotation_item / sales_quote_send_log）

- 模板 key+tpl_version 版本化，deleted 入唯一键（软删行写行 id，同 oa_form 模式）；
- 报价单金额服务端重算；quote_no 提交审批时发放（unique nullable，草稿不占号）；
- 发送留痕独立表（手动发送与 auto_send 都落行）。

Revision ID: i1a2b3c4d5e6
Revises: h1a2b3c4d5e6
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "i1a2b3c4d5e6"
down_revision = "h1a2b3c4d5e6"
branch_labels = None
depends_on = None

_BASE_COLS = [
    sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
    sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
    sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
    sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
    sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
    sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
    sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
]


def upgrade() -> None:
    op.create_table(
        "sales_quote_template",
        sa.Column("key", sa.String(64), nullable=False, comment="模板标识"),
        sa.Column("name", sa.String(128), nullable=False, comment="模板名称"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", comment="draft/published/disabled"),
        sa.Column("tpl_version", sa.Integer(), nullable=False, server_default="1", comment="模板版本"),
        sa.Column("layout_json", sa.Text(), nullable=True, comment="版式 JSON（抬头/说明/条款/页脚/明细列）"),
        sa.Column("sort", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "tpl_version", "deleted", name="uq_sales_quote_tpl_key_version"),
    )
    op.create_index("ix_sales_quote_template_key", "sales_quote_template", ["key"])
    op.create_index("ix_sales_quote_template_status", "sales_quote_template", ["status"])

    op.create_table(
        "sales_quotation",
        sa.Column("quote_no", sa.String(32), nullable=True, comment="报价编号 BJ…（提交审批时发放）"),
        sa.Column("title", sa.String(255), nullable=False, comment="报价标题"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="crm_customer.id"),
        sa.Column("customer_name", sa.String(128), nullable=False, server_default="", comment="客户名冗余"),
        sa.Column("contact_name", sa.String(64), nullable=False, server_default="", comment="客户联系人"),
        sa.Column("contact_phone", sa.String(32), nullable=False, server_default="", comment="联系人电话"),
        sa.Column("contact_email", sa.String(128), nullable=False, server_default="", comment="联系人邮箱"),
        sa.Column("template_id", sa.BigInteger(), nullable=True, comment="模板 sales_quote_template.id"),
        sa.Column("tpl_version", sa.Integer(), nullable=False, server_default="1", comment="模板版本快照引用"),
        sa.Column("layout_snapshot", sa.Text(), nullable=True, comment="模板版式快照 JSON"),
        sa.Column("requirement", sa.Text(), nullable=True, comment="客户需求描述（AI 生成输入）"),
        sa.Column("intro_html", sa.Text(), nullable=True, comment="报价说明"),
        sa.Column("terms_html", sa.Text(), nullable=True, comment="报价条款"),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0", comment="合计（服务端重算）"),
        sa.Column("tax_rate", sa.Numeric(5, 2), nullable=False, server_default="6", comment="税率 %"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("valid_until", sa.Date(), nullable=True, comment="报价有效期"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft",
                  comment="draft/approving/approved/rejected/sent/accepted/declined/voided"),
        sa.Column("ai_meta", sa.Text(), nullable=True, comment="AI 生成元信息 JSON"),
        sa.Column("auto_send", sa.Integer(), nullable=False, server_default="0", comment="审批通过自动发送 0/1"),
        sa.Column("sent_at", sa.DateTime(), nullable=True, comment="最近发送时间"),
        sa.Column("sent_channel", sa.String(16), nullable=False, server_default="", comment="最近发送通道"),
        sa.Column("sent_to", sa.String(255), nullable=False, server_default="", comment="最近发送收件人"),
        sa.Column("feedback_note", sa.String(500), nullable=False, server_default="", comment="客户反馈备注"),
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="审批实例"),
        sa.Column("contract_id", sa.BigInteger(), nullable=True, comment="转合同 ctr_contract.id（幂等）"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_no", name="uq_sales_quotation_quote_no"),
    )
    op.create_index("ix_sales_quotation_title", "sales_quotation", ["title"])
    op.create_index("ix_sales_quotation_customer_id", "sales_quotation", ["customer_id"])
    op.create_index("ix_sales_quotation_status", "sales_quotation", ["status"])
    op.create_index("ix_sales_quotation_flow_instance_id", "sales_quotation", ["flow_instance_id"])
    op.create_index("ix_sales_quotation_contract_id", "sales_quotation", ["contract_id"])

    op.create_table(
        "sales_quotation_item",
        sa.Column("quotation_id", sa.BigInteger(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="1", comment="行序"),
        sa.Column("name", sa.String(255), nullable=False, comment="项目名称"),
        sa.Column("spec", sa.String(255), nullable=False, server_default="", comment="规格说明"),
        sa.Column("unit", sa.String(16), nullable=False, server_default="", comment="单位"),
        sa.Column("qty", sa.Numeric(12, 2), nullable=False, comment="数量"),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False, comment="单价"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False, comment="金额（服务端重算）"),
        sa.Column("remark", sa.String(255), nullable=False, server_default=""),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["quotation_id"], ["sales_quotation.id"]),
    )
    op.create_index("ix_sales_quotation_item_quotation_id", "sales_quotation_item", ["quotation_id"])

    op.create_table(
        "sales_quote_send_log",
        sa.Column("quotation_id", sa.BigInteger(), nullable=False),
        sa.Column("channel", sa.String(16), nullable=False, comment="email/print/download"),
        sa.Column("recipient", sa.String(255), nullable=False, server_default="", comment="收件人"),
        sa.Column("result", sa.String(16), nullable=False, comment="real/debug/marked/skipped/failed"),
        sa.Column("detail", sa.String(500), nullable=False, server_default="", comment="结果说明/错误信息"),
        sa.Column("sender_id", sa.BigInteger(), nullable=True, comment="操作人（auto_send 为空）"),
        sa.Column("sender_name", sa.String(64), nullable=False, server_default=""),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["quotation_id"], ["sales_quotation.id"]),
    )
    op.create_index("ix_sales_quote_send_log_quotation_id", "sales_quote_send_log", ["quotation_id"])


def downgrade() -> None:
    op.drop_table("sales_quote_send_log")
    op.drop_table("sales_quotation_item")
    op.drop_table("sales_quotation")
    op.drop_table("sales_quote_template")
