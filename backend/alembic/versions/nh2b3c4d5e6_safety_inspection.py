"""B8 安全巡检管理（CSV 24）

新增表：
- `saf_inspection_plan`：巡检计划（周期 / 巡检项 / 负责人 / 下次巡检日期）；
- `saf_inspection`：巡检记录（逐项结果 / 异常项数 / 状态 draft·submitted·closed）；
- `saf_hazard`：隐患（整改 / 验证 / 关闭闭环）。

注意：`alembic/env.py` 未 import safety 域 models，**必须手写**本迁移，
否则 autogenerate 会试图删表。MySQL 不允许 TEXT 列带 DEFAULT，JSON 文本列在应用层兜底。

Revision ID: nh2b3c4d5e6
Revises: ng2b3c4d5e6
Create Date: 2026-11-26
"""

import sqlalchemy as sa

from alembic import op

revision = "nh2b3c4d5e6"
down_revision = "ng2b3c4d5e6"
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
        "saf_inspection_plan",
        sa.Column("plan_no", sa.String(32), nullable=False, comment="计划编号"),
        sa.Column("name", sa.String(128), nullable=False, server_default="", comment="计划名称"),
        sa.Column(
            "plan_type", sa.String(16), nullable=False, server_default="daily", comment="daily/weekly/monthly/special"
        ),
        sa.Column("target_area", sa.String(128), nullable=False, server_default="", comment="巡检区域 / 对象"),
        # MySQL 不允许 TEXT 列带 DEFAULT，值由 ORM 侧提供
        sa.Column("check_items", sa.Text(), nullable=False, comment="巡检项清单（JSON 数组字符串）"),
        sa.Column("cycle_days", sa.Integer(), nullable=False, server_default="1", comment="周期天数"),
        sa.Column("next_date", sa.Date(), nullable=True, comment="下次巡检日期"),
        sa.Column("owner_id", sa.BigInteger(), nullable=True, comment="负责人 id"),
        sa.Column("owner_name", sa.String(64), nullable=False, server_default="", comment="负责人姓名"),
        sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="归属部门 id"),
        sa.Column("dept_name", sa.String(128), nullable=False, server_default="", comment="归属部门"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active", comment="active/paused/finished"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_saf_inspection_plan_no", "saf_inspection_plan", ["plan_no"], unique=True)
    op.create_index("ix_saf_inspection_plan_plan_type", "saf_inspection_plan", ["plan_type"])
    op.create_index("ix_saf_inspection_plan_status", "saf_inspection_plan", ["status"])
    op.create_index("ix_saf_inspection_plan_next_date", "saf_inspection_plan", ["next_date"])

    op.create_table(
        "saf_inspection",
        sa.Column("record_no", sa.String(32), nullable=False, comment="记录编号"),
        sa.Column("plan_id", sa.BigInteger(), nullable=True, comment="关联计划 id"),
        sa.Column("plan_name", sa.String(128), nullable=False, server_default="", comment="关联计划名称"),
        sa.Column("area", sa.String(128), nullable=False, server_default="", comment="巡检区域"),
        sa.Column("inspect_date", sa.Date(), nullable=True, comment="巡检日期"),
        sa.Column("inspector_id", sa.BigInteger(), nullable=True, comment="巡检人 id"),
        sa.Column("inspector_name", sa.String(64), nullable=False, server_default="", comment="巡检人姓名"),
        sa.Column("result", sa.String(16), nullable=False, server_default="normal", comment="normal/abnormal"),
        sa.Column("abnormal_count", sa.Integer(), nullable=False, server_default="0", comment="异常项数"),
        sa.Column("items_json", sa.Text(), nullable=False, comment="逐项结果（JSON 数组字符串）"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", comment="draft/submitted/closed"),
        sa.Column("summary", sa.String(500), nullable=False, server_default="", comment="巡检小结"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_saf_inspection_record_no", "saf_inspection", ["record_no"], unique=True)
    op.create_index("ix_saf_inspection_plan_id", "saf_inspection", ["plan_id"])
    op.create_index("ix_saf_inspection_inspect_date", "saf_inspection", ["inspect_date"])
    op.create_index("ix_saf_inspection_result", "saf_inspection", ["result"])
    op.create_index("ix_saf_inspection_status", "saf_inspection", ["status"])

    op.create_table(
        "saf_hazard",
        sa.Column("hazard_no", sa.String(32), nullable=False, comment="隐患编号"),
        sa.Column("inspection_id", sa.BigInteger(), nullable=True, comment="来源巡检记录 id"),
        sa.Column("record_no", sa.String(32), nullable=False, server_default="", comment="来源巡检记录编号"),
        sa.Column("source", sa.String(16), nullable=False, server_default="inspection", comment="inspection/manual"),
        sa.Column("description", sa.String(500), nullable=False, server_default="", comment="隐患描述"),
        sa.Column("level", sa.String(16), nullable=False, server_default="medium", comment="low/medium/high/critical"),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="open", comment="open/rectifying/verified/closed"
        ),
        sa.Column("responsible_id", sa.BigInteger(), nullable=True, comment="责任人 id"),
        sa.Column("responsible_name", sa.String(64), nullable=False, server_default="", comment="责任人姓名"),
        sa.Column("deadline", sa.Date(), nullable=True, comment="整改期限"),
        sa.Column("found_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="发现时间"),
        sa.Column("measure", sa.String(500), nullable=False, server_default="", comment="整改措施"),
        sa.Column("rectified_at", sa.DateTime(), nullable=True, comment="整改完成时间"),
        sa.Column("rectified_by_name", sa.String(64), nullable=False, server_default="", comment="整改人姓名"),
        sa.Column("verify_result", sa.String(500), nullable=False, server_default="", comment="验证结论"),
        sa.Column("verify_by_name", sa.String(64), nullable=False, server_default="", comment="验证人姓名"),
        sa.Column("verified_at", sa.DateTime(), nullable=True, comment="验证时间"),
        sa.Column("remark", sa.String(255), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_saf_hazard_no", "saf_hazard", ["hazard_no"], unique=True)
    op.create_index("ix_saf_hazard_inspection_id", "saf_hazard", ["inspection_id"])
    op.create_index("ix_saf_hazard_level", "saf_hazard", ["level"])
    op.create_index("ix_saf_hazard_status", "saf_hazard", ["status"])
    op.create_index("ix_saf_hazard_deadline", "saf_hazard", ["deadline"])


def downgrade() -> None:
    op.drop_table("saf_hazard")
    op.drop_table("saf_inspection")
    op.drop_table("saf_inspection_plan")
