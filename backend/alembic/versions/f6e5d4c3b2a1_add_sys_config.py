"""add sys_config table (系统设置 key-value)

Revision ID: f6e5d4c3b2a1
Revises: e8f1a2b3c4d5
Create Date: 2026-10-09 16:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'f6e5d4c3b2a1'
down_revision = 'e8f1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'sys_config',
        sa.Column('key', sa.String(length=64), nullable=False, comment='配置键'),
        sa.Column('value', sa.Text(), nullable=False, comment='配置值（敏感项 AES-GCM 加密存储）'),
        sa.Column('remark', sa.String(length=255), nullable=False, comment='说明'),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sys_config_key'), 'sys_config', ['key'], unique=True)


def downgrade() -> None:
    op.drop_index(op.f('ix_sys_config_key'), table_name='sys_config')
    op.drop_table('sys_config')
