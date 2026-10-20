"""task numbering deferred to submit

草稿任务/样品不占正式编号：task_task.task_no 与 task_sample.sample_no 放宽为可空，
提交审批时才由编号规则发放（与合同 contract_no 语义一致）。

Revision ID: b8c9d0e1f2a3
Revises: f7a8b9c0d1e2
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2a3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("task_task", "task_no", type_=sa.String(32), existing_nullable=False, nullable=True)
    op.alter_column("task_sample", "sample_no", type_=sa.String(64), existing_nullable=False, nullable=True)


def downgrade() -> None:
    # 仅能把已有空号回填后才能恢复 NOT NULL；这里假定无空号或先人工处理
    op.alter_column("task_sample", "sample_no", type_=sa.String(64), existing_nullable=True, nullable=False)
    op.alter_column("task_task", "task_no", type_=sa.String(32), existing_nullable=True, nullable=False)
