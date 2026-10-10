"""finance links (settlement contract/customer) + contact fields

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-10-10 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'c1d2e3f4a5b6'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('fin_settlement', sa.Column('contract_id', sa.BigInteger(), nullable=True, comment='ctr_contract.id'))
    op.add_column('fin_settlement', sa.Column('customer_id', sa.BigInteger(), nullable=True, comment='crm_customer.id'))
    op.create_index(op.f('ix_fin_settlement_contract_id'), 'fin_settlement', ['contract_id'], unique=False)
    op.create_index(op.f('ix_fin_settlement_customer_id'), 'fin_settlement', ['customer_id'], unique=False)
    # 从任务回填合同/客户关联
    op.execute(
        'UPDATE fin_settlement s JOIN task_task t ON s.task_id = t.id '
        'SET s.contract_id = t.contract_id, s.customer_id = t.customer_id'
    )
    op.add_column('crm_customer', sa.Column('contact_person', sa.String(length=64), nullable=True, comment='联系人'))
    op.add_column('crm_customer', sa.Column('contact_phone', sa.String(length=32), nullable=True, comment='联系电话'))
    op.add_column('ctr_contract', sa.Column('contact_person', sa.String(length=64), nullable=True, comment='联系人'))
    op.add_column('ctr_contract', sa.Column('contact_phone', sa.String(length=32), nullable=True, comment='联系电话'))


def downgrade() -> None:
    op.drop_column('ctr_contract', 'contact_phone')
    op.drop_column('ctr_contract', 'contact_person')
    op.drop_column('crm_customer', 'contact_phone')
    op.drop_column('crm_customer', 'contact_person')
    op.drop_index(op.f('ix_fin_settlement_customer_id'), table_name='fin_settlement')
    op.drop_index(op.f('ix_fin_settlement_contract_id'), table_name='fin_settlement')
    op.drop_column('fin_settlement', 'customer_id')
    op.drop_column('fin_settlement', 'contract_id')
