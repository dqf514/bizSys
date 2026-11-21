"""F5：全流程驱动 —— 单据接入审批引擎的支撑列

- prj_project 新增 flow_instance_id（立项审批实例）
- hr_timesheet 新增 flow_instance_id（工时审批实例）
- fin_payment 新增 status / flow_instance_id（回款复核流程；存量行置 confirmed）
- ast_disposal 新增 flow_instance_id（处置审批实例）
- ast_receipt 新增 flow_instance_id（验收审批实例）
- rpt_report 新增 seal_flow_instance_id（用章申请审批实例）

project / hr 域不在 alembic/env.py 的 metadata 里（与 oa/procurement/sales 同理），
因此本迁移手写。

Revision ID: n6a2b3c4d5e6
Revises: n5a2b3c4d5e6
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

revision = "n6a2b3c4d5e6"
down_revision = "n5a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------- 项目立项 ----------------
    op.add_column(
        "prj_project",
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="立项审批实例 approval_instance.id"),
    )
    op.create_index("ix_prj_project_flow_instance_id", "prj_project", ["flow_instance_id"])

    # ---------------- 工时填报 ----------------
    op.add_column(
        "hr_timesheet",
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="工时审批实例 approval_instance.id"),
    )
    op.create_index("ix_hr_timesheet_flow_instance_id", "hr_timesheet", ["flow_instance_id"])

    # ---------------- 回款复核 ----------------
    op.add_column(
        "fin_payment",
        sa.Column("status", sa.String(16), nullable=True, server_default="draft", comment="draft/approving/confirmed/rejected"),
    )
    op.add_column(
        "fin_payment",
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="回款复核审批实例 approval_instance.id"),
    )
    op.create_index("ix_fin_payment_status", "fin_payment", ["status"])
    op.create_index("ix_fin_payment_flow_instance_id", "fin_payment", ["flow_instance_id"])
    # 存量回款单据已是既成事实，直接置为已确认（不影响既有统计口径）
    op.execute("UPDATE fin_payment SET status = 'confirmed' WHERE status IS NULL OR status = 'draft'")

    # ---------------- 资产处置 / 到货验收 ----------------
    op.add_column(
        "ast_disposal",
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="处置审批实例 approval_instance.id"),
    )
    op.create_index("ix_ast_disposal_flow_instance_id", "ast_disposal", ["flow_instance_id"])
    op.add_column(
        "ast_receipt",
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="验收审批实例 approval_instance.id"),
    )
    op.create_index("ix_ast_receipt_flow_instance_id", "ast_receipt", ["flow_instance_id"])

    # ---------------- 报告用章 ----------------
    op.add_column(
        "rpt_report",
        sa.Column("seal_flow_instance_id", sa.BigInteger(), nullable=True, comment="用章申请审批实例 approval_instance.id"),
    )
    op.create_index("ix_rpt_report_seal_flow_instance_id", "rpt_report", ["seal_flow_instance_id"])


def downgrade() -> None:
    op.drop_index("ix_rpt_report_seal_flow_instance_id", table_name="rpt_report")
    op.drop_column("rpt_report", "seal_flow_instance_id")

    op.drop_index("ix_ast_receipt_flow_instance_id", table_name="ast_receipt")
    op.drop_column("ast_receipt", "flow_instance_id")
    op.drop_index("ix_ast_disposal_flow_instance_id", table_name="ast_disposal")
    op.drop_column("ast_disposal", "flow_instance_id")

    op.drop_index("ix_fin_payment_flow_instance_id", table_name="fin_payment")
    op.drop_index("ix_fin_payment_status", table_name="fin_payment")
    op.drop_column("fin_payment", "flow_instance_id")
    op.drop_column("fin_payment", "status")

    op.drop_index("ix_hr_timesheet_flow_instance_id", table_name="hr_timesheet")
    op.drop_column("hr_timesheet", "flow_instance_id")

    op.drop_index("ix_prj_project_flow_instance_id", table_name="prj_project")
    op.drop_column("prj_project", "flow_instance_id")
