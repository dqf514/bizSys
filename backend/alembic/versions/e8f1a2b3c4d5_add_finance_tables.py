"""add finance tables (fin_settlement / fin_invoice / fin_payment)

Revision ID: e8f1a2b3c4d5
Revises: 587ddff7c998
Create Date: 2026-10-09 22:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'e8f1a2b3c4d5'
down_revision = '587ddff7c998'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fin_settlement',
        sa.Column('settlement_no', sa.String(length=32), nullable=False, comment='结算单号 HK...'),
        sa.Column('task_id', sa.BigInteger(), nullable=False, comment='task_task.id（一任务一结算单）'),
        sa.Column('task_no', sa.String(length=32), nullable=False, comment='任务编号冗余'),
        sa.Column('contract_no', sa.String(length=32), nullable=False, comment='合同号冗余'),
        sa.Column('customer_name', sa.String(length=128), nullable=False, comment='客户名冗余'),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, comment='结算金额'),
        sa.Column('invoiceable_amount', sa.Numeric(precision=18, scale=2), nullable=False, comment='可开票金额'),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('approval_instance_id', sa.BigInteger(), nullable=True, comment='最近一次开票审批实例'),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fin_settlement_status_update_time', 'fin_settlement', ['status', 'update_time'])
    op.create_index(op.f('ix_fin_settlement_settlement_no'), 'fin_settlement', ['settlement_no'], unique=True)
    op.create_index(op.f('ix_fin_settlement_status'), 'fin_settlement', ['status'])
    op.create_index(op.f('ix_fin_settlement_task_id'), 'fin_settlement', ['task_id'], unique=True)
    op.create_index(op.f('ix_fin_settlement_approval_instance_id'), 'fin_settlement', ['approval_instance_id'])

    op.create_table(
        'fin_invoice',
        sa.Column('settlement_id', sa.BigInteger(), nullable=False, comment='fin_settlement.id'),
        sa.Column('invoice_no', sa.String(length=64), nullable=True, comment='发票号（财务后补）'),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, comment='开票金额'),
        sa.Column('invoice_date', sa.Date(), nullable=True, comment='开票日期'),
        sa.Column('status', sa.String(length=16), nullable=False, comment='approving/issued'),
        sa.Column('approval_instance_id', sa.BigInteger(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fin_invoice_settlement_id'), 'fin_invoice', ['settlement_id'])

    op.create_table(
        'fin_payment',
        sa.Column('payment_no', sa.String(length=32), nullable=False, comment='到账单号 DZ...'),
        sa.Column('settlement_id', sa.BigInteger(), nullable=False, comment='fin_settlement.id'),
        sa.Column('pay_type', sa.String(length=32), nullable=False, comment='字典 pay_type'),
        sa.Column('payer_name', sa.String(length=128), nullable=False, comment='付款方名称'),
        sa.Column('payer_account', sa.String(length=64), nullable=False, comment='付款方账号'),
        sa.Column('amount', sa.Numeric(precision=18, scale=2), nullable=False, comment='到账金额'),
        sa.Column('bank', sa.String(length=128), nullable=False, comment='付款银行'),
        sa.Column('paid_at', sa.Date(), nullable=False, comment='到账日期'),
        sa.Column('remark', sa.Text(), nullable=True),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fin_payment_settlement_update_time', 'fin_payment', ['settlement_id', 'update_time'])
    op.create_index(op.f('ix_fin_payment_payment_no'), 'fin_payment', ['payment_no'], unique=True)
    op.create_index(op.f('ix_fin_payment_settlement_id'), 'fin_payment', ['settlement_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_fin_payment_settlement_id'), table_name='fin_payment')
    op.drop_index(op.f('ix_fin_payment_payment_no'), table_name='fin_payment')
    op.drop_index('ix_fin_payment_settlement_update_time', table_name='fin_payment')
    op.drop_table('fin_payment')
    op.drop_index(op.f('ix_fin_invoice_settlement_id'), table_name='fin_invoice')
    op.drop_table('fin_invoice')
    op.drop_index(op.f('ix_fin_settlement_approval_instance_id'), table_name='fin_settlement')
    op.drop_index(op.f('ix_fin_settlement_task_id'), table_name='fin_settlement')
    op.drop_index(op.f('ix_fin_settlement_status'), table_name='fin_settlement')
    op.drop_index(op.f('ix_fin_settlement_settlement_no'), table_name='fin_settlement')
    op.drop_index('ix_fin_settlement_status_update_time', table_name='fin_settlement')
    op.drop_table('fin_settlement')
