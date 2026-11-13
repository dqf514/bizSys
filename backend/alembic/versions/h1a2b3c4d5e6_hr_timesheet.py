"""人事行政：工时填报 hr_timesheet

- 一条 = 某用户某天某任务一条工时；(user_id, work_date, task_id, deleted) 唯一，
  软删行写行 id 避免与历史软删行互撞（同 oa_form 模式）；
- 任务/合同/客户快照落行；hours Numeric(4,1)（0.5 步进由应用层校验，≤24）。

Revision ID: h1a2b3c4d5e6
Revises: g1a2b3c4d5e6
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "h1a2b3c4d5e6"
down_revision = "g1a2b3c4d5e6"
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
        "hr_timesheet",
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="填报人 sys_user.id"),
        sa.Column("user_name", sa.String(64), nullable=False, server_default="", comment="填报人姓名冗余"),
        sa.Column("work_date", sa.Date(), nullable=False, comment="工作日期（不允许未来日期）"),
        sa.Column("task_id", sa.BigInteger(), nullable=False, comment="关联任务 task_task.id"),
        sa.Column("task_no", sa.String(32), nullable=False, server_default="", comment="任务编号快照"),
        sa.Column("task_name", sa.String(255), nullable=False, server_default="", comment="任务名称快照"),
        sa.Column("contract_id", sa.BigInteger(), nullable=False, comment="关联合同快照"),
        sa.Column("contract_no", sa.String(32), nullable=False, server_default="", comment="合同号快照"),
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="客户快照"),
        sa.Column("customer_name", sa.String(128), nullable=False, server_default="", comment="客户名快照"),
        sa.Column("hours", sa.Numeric(4, 1), nullable=False, comment="工时小时数（0.5 步进，≤24）"),
        sa.Column("content", sa.String(500), nullable=False, server_default="", comment="工作内容"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", comment="draft/submitted"),
        sa.Column("submitted_at", sa.DateTime(), nullable=True, comment="最近提交时间"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["task_task.id"]),
        sa.UniqueConstraint("user_id", "work_date", "task_id", "deleted", name="uq_hr_timesheet_user_date_task"),
    )
    op.create_index("ix_hr_timesheet_user_id", "hr_timesheet", ["user_id"])
    op.create_index("ix_hr_timesheet_work_date", "hr_timesheet", ["work_date"])
    op.create_index("ix_hr_timesheet_task_id", "hr_timesheet", ["task_id"])
    op.create_index("ix_hr_timesheet_contract_id", "hr_timesheet", ["contract_id"])
    op.create_index("ix_hr_timesheet_customer_id", "hr_timesheet", ["customer_id"])
    op.create_index("ix_hr_timesheet_status", "hr_timesheet", ["status"])


def downgrade() -> None:
    op.drop_table("hr_timesheet")
