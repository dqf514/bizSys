"""F3 flow-driven: contract_no nullable（draft 不占正式 HT 编号，提交时发放）

Revision ID: b3c4d5e6f7a8
Revises: a1b2c3d4e5f6
Create Date: 2026-10-19 13:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'b3c4d5e6f7a8'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MySQL 唯一索引允许多个 NULL：draft 合同 contract_no 置空不冲突
    op.alter_column('ctr_contract', 'contract_no', existing_type=sa.String(length=32), nullable=True,
                    comment='合同编号 HT...（提交审批时发放，draft 为空）')
    op.add_column('task_task', sa.Column('flow_instance_id', sa.BigInteger(), nullable=True))
    op.create_index('ix_task_task_flow_instance_id', 'task_task', ['flow_instance_id'])


def downgrade() -> None:
    op.drop_index('ix_task_task_flow_instance_id', table_name='task_task')
    op.drop_column('task_task', 'flow_instance_id')
    op.alter_column('ctr_contract', 'contract_no', existing_type=sa.String(length=32), nullable=False,
                    comment='合同编号 HT...')
