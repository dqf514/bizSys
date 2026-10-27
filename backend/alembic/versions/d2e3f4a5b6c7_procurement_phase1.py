"""procurement phase-1：往来单位扩展 + 采购申请/合同/出入库五表

- crm_customer 加 partner_type（customer/supplier/both，默认 customer，存量回填）、
  supply_category、supplier_rating；
- 新建 pur_request / pur_request_item / pur_contract / pur_stock_order / pur_stock_item。

Revision ID: d2e3f4a5b6c7
Revises: b1c2d3e4f5a6
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "d2e3f4a5b6c7"
down_revision = "b1c2d3e4f5a6"
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
    op.add_column(
        "crm_customer",
        sa.Column("partner_type", sa.String(16), nullable=False, server_default="customer",
                  comment="customer/supplier/both"),
    )
    op.add_column(
        "crm_customer",
        sa.Column("supply_category", sa.String(32), nullable=False, server_default="", comment="字典 supply_category（供应商）"),
    )
    op.add_column(
        "crm_customer",
        sa.Column("supplier_rating", sa.String(8), nullable=False, server_default="", comment="复用字典 customer_grade（供应商评级）"),
    )
    op.create_index("ix_crm_customer_partner_type", "crm_customer", ["partner_type"])

    op.create_table(
        "pur_request",
        sa.Column("request_no", sa.String(32), nullable=True, comment="申请编号 PR...（提交审批时发放，draft 为空）"),
        sa.Column("title", sa.String(255), nullable=False, comment="申请标题"),
        sa.Column("task_id", sa.BigInteger(), nullable=True, comment="关联任务 tk_task.id"),
        sa.Column("task_no", sa.String(32), nullable=False, server_default="", comment="任务编号冗余"),
        sa.Column("task_name", sa.String(255), nullable=False, server_default="", comment="任务名称冗余"),
        sa.Column("purchase_method", sa.String(32), nullable=False, server_default="", comment="字典 purchase_method"),
        sa.Column("budget_amount", sa.Numeric(14, 2), nullable=True, comment="预算金额"),
        sa.Column("expect_date", sa.Date(), nullable=True, comment="期望到货日期"),
        sa.Column("reason", sa.Text(), nullable=True, comment="采购事由"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_no"),
    )
    op.create_index("ix_pur_request_request_no", "pur_request", ["request_no"])
    op.create_index("ix_pur_request_title", "pur_request", ["title"])
    op.create_index("ix_pur_request_task_id", "pur_request", ["task_id"])
    op.create_index("ix_pur_request_status", "pur_request", ["status"])
    op.create_index("ix_pur_request_flow_instance_id", "pur_request", ["flow_instance_id"])

    op.create_table(
        "pur_request_item",
        sa.Column("request_id", sa.BigInteger(), nullable=False),
        sa.Column("item_name", sa.String(255), nullable=False, comment="物资名称"),
        sa.Column("spec", sa.String(255), nullable=False, server_default="", comment="规格型号"),
        sa.Column("unit", sa.String(16), nullable=False, server_default="", comment="单位"),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, comment="数量"),
        sa.Column("estimate_price", sa.Numeric(14, 2), nullable=True, comment="预估单价"),
        sa.Column("remark", sa.String(500), nullable=False, server_default=""),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["request_id"], ["pur_request.id"]),
    )
    op.create_index("ix_pur_request_item_request_id", "pur_request_item", ["request_id"])

    op.create_table(
        "pur_contract",
        sa.Column("contract_no", sa.String(32), nullable=True, comment="合同编号 CG...（提交审批时发放）"),
        sa.Column("name", sa.String(255), nullable=False, comment="合同名称"),
        sa.Column("request_id", sa.BigInteger(), nullable=True, comment="来源采购申请"),
        sa.Column("request_no", sa.String(32), nullable=False, server_default="", comment="申请编号冗余"),
        sa.Column("supplier_id", sa.BigInteger(), nullable=False, comment="供应商 crm_customer.id"),
        sa.Column("supplier_name", sa.String(128), nullable=False, server_default="", comment="供应商名冗余"),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True, comment="合同金额"),
        sa.Column("sign_date", sa.Date(), nullable=True, comment="签订日期"),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("pay_cycle", sa.String(32), nullable=False, server_default="", comment="字典 pay_cycle"),
        sa.Column("delivery", sa.String(32), nullable=False, server_default="", comment="字典 delivery_way"),
        sa.Column("handler_id", sa.BigInteger(), nullable=True, comment="经办人"),
        sa.Column("handler_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_no"),
    )
    op.create_index("ix_pur_contract_contract_no", "pur_contract", ["contract_no"])
    op.create_index("ix_pur_contract_name", "pur_contract", ["name"])
    op.create_index("ix_pur_contract_request_id", "pur_contract", ["request_id"])
    op.create_index("ix_pur_contract_supplier_id", "pur_contract", ["supplier_id"])
    op.create_index("ix_pur_contract_status", "pur_contract", ["status"])
    op.create_index("ix_pur_contract_flow_instance_id", "pur_contract", ["flow_instance_id"])

    op.create_table(
        "pur_stock_order",
        sa.Column("order_no", sa.String(32), nullable=False, comment="单号 RK.../CK...（登记即发放）"),
        sa.Column("order_type", sa.String(8), nullable=False, comment="in 入库 / out 出库"),
        sa.Column("contract_id", sa.BigInteger(), nullable=True, comment="关联采购合同"),
        sa.Column("contract_no", sa.String(32), nullable=False, server_default="", comment="采购合同号冗余"),
        sa.Column("contract_name", sa.String(255), nullable=False, server_default="", comment="采购合同名冗余"),
        sa.Column("warehouse", sa.String(32), nullable=False, server_default="", comment="字典 warehouse"),
        sa.Column("handler_id", sa.BigInteger(), nullable=True, comment="经办人"),
        sa.Column("handler_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("order_date", sa.Date(), nullable=True, comment="出入库日期"),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="registered"),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="", comment="来源类型（二期预留）"),
        sa.Column("source_id", sa.BigInteger(), nullable=True, comment="来源单据（二期预留）"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_no"),
    )
    op.create_index("ix_pur_stock_order_order_no", "pur_stock_order", ["order_no"])
    op.create_index("ix_pur_stock_order_order_type", "pur_stock_order", ["order_type"])
    op.create_index("ix_pur_stock_order_contract_id", "pur_stock_order", ["contract_id"])
    op.create_index("ix_pur_stock_order_status", "pur_stock_order", ["status"])

    op.create_table(
        "pur_stock_item",
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("item_name", sa.String(255), nullable=False, comment="物资名称"),
        sa.Column("spec", sa.String(255), nullable=False, server_default="", comment="规格型号"),
        sa.Column("unit", sa.String(16), nullable=False, server_default="", comment="单位"),
        sa.Column("quantity", sa.Numeric(12, 2), nullable=False, comment="数量"),
        sa.Column("price", sa.Numeric(14, 2), nullable=True, comment="单价"),
        sa.Column("remark", sa.String(500), nullable=False, server_default=""),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["order_id"], ["pur_stock_order.id"]),
    )
    op.create_index("ix_pur_stock_item_order_id", "pur_stock_item", ["order_id"])


def downgrade() -> None:
    op.drop_table("pur_stock_item")
    op.drop_table("pur_stock_order")
    op.drop_table("pur_contract")
    op.drop_table("pur_request_item")
    op.drop_table("pur_request")
    op.drop_index("ix_crm_customer_partner_type", table_name="crm_customer")
    op.drop_column("crm_customer", "supplier_rating")
    op.drop_column("crm_customer", "supply_category")
    op.drop_column("crm_customer", "partner_type")
