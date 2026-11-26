"""B6 设备台账 / 设备能耗采集 / 设备预警

新增三张表：
- `ast_equipment`         设备台账
- `ast_equipment_metric`  设备能耗与运行数据（按日 + 班次）
- `ast_equipment_alert`   设备预警

手写迁移：`alembic/env.py` 未 import asset 域新增模型，autogenerate 会误删表。

Revision ID: ng2b3c4d5e6
Revises: nf2b3c4d5e6
Create Date: 2026-11-26
"""

import sqlalchemy as sa

from alembic import op

revision = "ng2b3c4d5e6"
down_revision = "nf2b3c4d5e6"
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
    # ---------------- ast_equipment ----------------
    op.create_table(
        "ast_equipment",
        sa.Column("equipment_no", sa.String(32), nullable=False, comment="设备编号"),
        sa.Column("name", sa.String(128), nullable=True, comment="设备名称"),
        sa.Column("category", sa.String(32), nullable=True, comment="设备类别 wind_tunnel/cfd/machining/test/other"),
        sa.Column("model", sa.String(64), nullable=True, comment="型号"),
        sa.Column("spec", sa.String(255), nullable=True, comment="规格"),
        sa.Column("workshop", sa.String(64), nullable=True, comment="所属车间/区域"),
        sa.Column("location", sa.String(128), nullable=True, comment="安装位置"),
        sa.Column("vendor_id", sa.BigInteger(), nullable=True, comment="供应商 crm_customer.id"),
        sa.Column("vendor_name", sa.String(128), nullable=True, comment="供应商名冗余"),
        sa.Column("purchase_date", sa.Date(), nullable=True, comment="购置日期"),
        sa.Column("commission_date", sa.Date(), nullable=True, comment="投产日期"),
        sa.Column("original_value", sa.Numeric(14, 2), nullable=True, comment="原值"),
        sa.Column("status", sa.String(16), nullable=True, comment="idle/running/maintenance/fault/scrapped"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True, comment="责任人 sys_user.id"),
        sa.Column("owner_name", sa.String(64), nullable=True, comment="责任人姓名"),
        sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="使用部门 sys_dept.id"),
        sa.Column("dept_name", sa.String(128), nullable=True, comment="使用部门名冗余"),
        sa.Column("maintain_cycle_days", sa.Integer(), nullable=True, comment="保养周期（天，0=不启用）"),
        sa.Column("last_maintain_date", sa.Date(), nullable=True, comment="上次保养日期"),
        sa.Column("next_maintain_date", sa.Date(), nullable=True, comment="下次保养日期"),
        sa.Column("run_hours", sa.Numeric(12, 2), nullable=True, comment="累计运行工时"),
        sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ast_equipment_equipment_no", "ast_equipment", ["equipment_no"], unique=True)
    op.create_index("ix_ast_equipment_name", "ast_equipment", ["name"], unique=False)
    op.create_index("ix_ast_equipment_category", "ast_equipment", ["category"], unique=False)
    op.create_index("ix_ast_equipment_workshop", "ast_equipment", ["workshop"], unique=False)
    op.create_index("ix_ast_equipment_vendor_id", "ast_equipment", ["vendor_id"], unique=False)
    op.create_index("ix_ast_equipment_status", "ast_equipment", ["status"], unique=False)
    op.create_index("ix_ast_equipment_dept_id", "ast_equipment", ["dept_id"], unique=False)
    op.create_index("ix_ast_equipment_next_maintain_date", "ast_equipment", ["next_maintain_date"], unique=False)

    # ---------------- ast_equipment_metric ----------------
    op.create_table(
        "ast_equipment_metric",
        sa.Column("equipment_id", sa.BigInteger(), nullable=True, comment="设备 ast_equipment.id"),
        sa.Column("equipment_no", sa.String(32), nullable=True, comment="设备编号冗余"),
        sa.Column("equipment_name", sa.String(128), nullable=True, comment="设备名称冗余"),
        sa.Column("stat_date", sa.Date(), nullable=True, comment="统计日期"),
        sa.Column("shift", sa.String(16), nullable=True, comment="班次 morning/day/night"),
        sa.Column("run_hours", sa.Numeric(10, 2), nullable=True, comment="运行工时"),
        sa.Column("downtime_hours", sa.Numeric(10, 2), nullable=True, comment="停机工时"),
        sa.Column("energy", sa.Numeric(12, 2), nullable=True, comment="能耗 kWh"),
        sa.Column("output_qty", sa.Numeric(12, 2), nullable=True, comment="产量/台次"),
        sa.Column("source", sa.String(16), nullable=True, comment="来源 manual/schedule"),
        sa.Column("remark", sa.String(255), nullable=True, comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ast_equipment_metric_equipment_id", "ast_equipment_metric", ["equipment_id"], unique=False)
    op.create_index("ix_ast_equipment_metric_stat_date", "ast_equipment_metric", ["stat_date"], unique=False)

    # ---------------- ast_equipment_alert ----------------
    op.create_table(
        "ast_equipment_alert",
        sa.Column("alert_no", sa.String(32), nullable=False, comment="预警单号"),
        sa.Column("equipment_id", sa.BigInteger(), nullable=True, comment="设备 ast_equipment.id"),
        sa.Column("equipment_no", sa.String(32), nullable=True, comment="设备编号冗余"),
        sa.Column("equipment_name", sa.String(128), nullable=True, comment="设备名称冗余"),
        sa.Column(
            "rule_type",
            sa.String(32),
            nullable=True,
            comment="maintain_overdue/energy_abnormal/low_utilization/fault/status_abnormal",
        ),
        sa.Column("level", sa.String(16), nullable=True, comment="级别 info/warning/critical"),
        sa.Column("title", sa.String(128), nullable=True, comment="预警标题"),
        sa.Column("content", sa.String(500), nullable=True, comment="预警内容"),
        sa.Column("status", sa.String(16), nullable=True, comment="open/processing/closed"),
        sa.Column("triggered_at", sa.DateTime(), nullable=True, comment="触发时间"),
        sa.Column("handler_id", sa.BigInteger(), nullable=True, comment="处理人 sys_user.id"),
        sa.Column("handler_name", sa.String(64), nullable=True, comment="处理人姓名"),
        sa.Column("handled_at", sa.DateTime(), nullable=True, comment="处理时间"),
        sa.Column("handle_result", sa.String(500), nullable=True, comment="处理结果"),
        sa.Column("remark", sa.String(255), nullable=True, comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ast_equipment_alert_alert_no", "ast_equipment_alert", ["alert_no"], unique=True)
    op.create_index("ix_ast_equipment_alert_equipment_id", "ast_equipment_alert", ["equipment_id"], unique=False)
    op.create_index("ix_ast_equipment_alert_rule_type", "ast_equipment_alert", ["rule_type"], unique=False)
    op.create_index("ix_ast_equipment_alert_status", "ast_equipment_alert", ["status"], unique=False)
    op.create_index("ix_ast_equipment_alert_triggered_at", "ast_equipment_alert", ["triggered_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ast_equipment_alert_triggered_at", table_name="ast_equipment_alert")
    op.drop_index("ix_ast_equipment_alert_status", table_name="ast_equipment_alert")
    op.drop_index("ix_ast_equipment_alert_rule_type", table_name="ast_equipment_alert")
    op.drop_index("ix_ast_equipment_alert_equipment_id", table_name="ast_equipment_alert")
    op.drop_index("ix_ast_equipment_alert_alert_no", table_name="ast_equipment_alert")
    op.drop_table("ast_equipment_alert")

    op.drop_index("ix_ast_equipment_metric_stat_date", table_name="ast_equipment_metric")
    op.drop_index("ix_ast_equipment_metric_equipment_id", table_name="ast_equipment_metric")
    op.drop_table("ast_equipment_metric")

    op.drop_index("ix_ast_equipment_next_maintain_date", table_name="ast_equipment")
    op.drop_index("ix_ast_equipment_dept_id", table_name="ast_equipment")
    op.drop_index("ix_ast_equipment_status", table_name="ast_equipment")
    op.drop_index("ix_ast_equipment_vendor_id", table_name="ast_equipment")
    op.drop_index("ix_ast_equipment_workshop", table_name="ast_equipment")
    op.drop_index("ix_ast_equipment_category", table_name="ast_equipment")
    op.drop_index("ix_ast_equipment_name", table_name="ast_equipment")
    op.drop_index("ix_ast_equipment_equipment_no", table_name="ast_equipment")
    op.drop_table("ast_equipment")
