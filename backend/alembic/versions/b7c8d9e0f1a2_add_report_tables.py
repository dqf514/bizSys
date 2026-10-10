"""add report tables (rpt_file / rpt_report)

Revision ID: b7c8d9e0f1a2
Revises: f6e5d4c3b2a1
Create Date: 2026-10-10 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'b7c8d9e0f1a2'
down_revision = 'f6e5d4c3b2a1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'rpt_file',
        sa.Column('file_name', sa.String(length=255), nullable=False, comment='原始文件名'),
        sa.Column('size', sa.BigInteger(), nullable=False, comment='字节数'),
        sa.Column('content_type', sa.String(length=128), nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False, comment='相对 upload_dir 的路径'),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'rpt_report',
        sa.Column('report_no', sa.String(length=32), nullable=False, comment='报告编号 BG...（取自条目）'),
        sa.Column('task_id', sa.BigInteger(), nullable=False, comment='task_task.id'),
        sa.Column('task_item_id', sa.BigInteger(), nullable=False, comment='task_item.id（一条目一未删报告）'),
        sa.Column('file_id', sa.BigInteger(), nullable=False, comment='原件 rpt_file.id'),
        sa.Column('file_name', sa.String(length=255), nullable=False, comment='原件文件名冗余'),
        sa.Column('status', sa.String(length=16), nullable=False, comment='uploaded/approving/approved/rejected/sealed'),
        sa.Column('pdf_file_id', sa.BigInteger(), nullable=True, comment='转换后 PDF rpt_file.id'),
        sa.Column('seal_by', sa.BigInteger(), nullable=True, comment='签章人'),
        sa.Column('seal_time', sa.DateTime(), nullable=True, comment='签章时间'),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('approval_instance_id', sa.BigInteger(), nullable=True, comment='最近一次签批审批实例'),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_rpt_report_report_no'), 'rpt_report', ['report_no'], unique=True)
    op.create_index(op.f('ix_rpt_report_task_id'), 'rpt_report', ['task_id'], unique=False)
    op.create_index(op.f('ix_rpt_report_task_item_id'), 'rpt_report', ['task_item_id'], unique=False)
    op.create_index(op.f('ix_rpt_report_file_id'), 'rpt_report', ['file_id'], unique=False)
    op.create_index(op.f('ix_rpt_report_status'), 'rpt_report', ['status'], unique=False)
    op.create_index(op.f('ix_rpt_report_approval_instance_id'), 'rpt_report', ['approval_instance_id'], unique=False)
    op.create_index('ix_rpt_report_status_update_time', 'rpt_report', ['status', 'update_time'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_rpt_report_status_update_time', table_name='rpt_report')
    op.drop_index(op.f('ix_rpt_report_approval_instance_id'), table_name='rpt_report')
    op.drop_index(op.f('ix_rpt_report_status'), table_name='rpt_report')
    op.drop_index(op.f('ix_rpt_report_file_id'), table_name='rpt_report')
    op.drop_index(op.f('ix_rpt_report_task_item_id'), table_name='rpt_report')
    op.drop_index(op.f('ix_rpt_report_task_id'), table_name='rpt_report')
    op.drop_index(op.f('ix_rpt_report_report_no'), table_name='rpt_report')
    op.drop_table('rpt_report')
    op.drop_table('rpt_file')
