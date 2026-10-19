"""workflow engine merge: node types, variables, cc, view state

F1 工作流引擎合并（对齐 TPCworkflow 语义）：
- approval_definition 增加 process_graph / variables_schema；
- approval_node 增加 node_type / sign_mode / branches / default_seq；
- approval_instance 增加 variables / current_node_ids；
- approval_task 增加 node_type / action_meta；
- approval_record 增加 payload；
- 新增 approval_cc / approval_view_state。

Revision ID: a1b2c3d4e5f6
Revises: c1d2e3f4a5b6
Create Date: 2026-11-21 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('approval_definition', sa.Column('process_graph', sa.Text(), nullable=True,
                                                   comment='LogicFlow 图 JSON（线性定义自动生成等价图）'))
    op.add_column('approval_definition', sa.Column('variables_schema', sa.Text(), nullable=True,
                                                   comment='流程变量声明 JSON'))
    op.add_column('approval_node', sa.Column('node_type', sa.String(length=16), nullable=False,
                                             server_default='approval', comment='approval/condition/cc'))
    op.add_column('approval_node', sa.Column('sign_mode', sa.String(length=16), nullable=False,
                                             server_default='or', comment='or/and/sequential（仅审批节点）'))
    op.add_column('approval_node', sa.Column('branches', sa.Text(), nullable=True,
                                             comment='条件分支 JSON：[{expr:{field,op,value},targetSeq}]'))
    op.add_column('approval_node', sa.Column('default_seq', sa.Integer(), nullable=True,
                                             comment='条件未命中时跳转序号（空=顺序下一节点）'))
    op.add_column('approval_instance', sa.Column('current_node_ids', sa.Text(), nullable=True,
                                                 comment='当前节点序号 JSON 数组'))
    op.add_column('approval_instance', sa.Column('variables', sa.Text(), nullable=True,
                                                 comment='流程变量 JSON（发起时注入）'))
    op.add_column('approval_task', sa.Column('node_type', sa.String(length=16), nullable=False,
                                             server_default='approval', comment='approval（冗余节点类型）'))
    op.add_column('approval_task', sa.Column('action_meta', sa.Text(), nullable=True,
                                             comment='依次队列 sequential_queue/index、加签来源等 JSON'))
    op.add_column('approval_record', sa.Column('payload', sa.Text(), nullable=True, comment='动作附带数据 JSON'))

    op.create_table(
        'approval_cc',
        sa.Column('instance_id', sa.BigInteger(), nullable=False),
        sa.Column('seq', sa.Integer(), nullable=False, comment='产生抄送的节点序号'),
        sa.Column('node_name', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('user_name', sa.String(length=64), nullable=False),
        sa.Column('read_at', sa.DateTime(), nullable=True, comment='已读时间（空=未读）'),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.ForeignKeyConstraint(['instance_id'], ['approval_instance.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approval_cc_instance_id'), 'approval_cc', ['instance_id'], unique=False)
    op.create_index(op.f('ix_approval_cc_user_id'), 'approval_cc', ['user_id'], unique=False)
    op.create_table(
        'approval_view_state',
        sa.Column('user_id', sa.BigInteger(), nullable=False),
        sa.Column('instance_id', sa.BigInteger(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False, comment='主键'),
        sa.Column('create_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='创建时间'),
        sa.Column('create_by', sa.BigInteger(), nullable=True, comment='创建人'),
        sa.Column('update_time', sa.DateTime(), server_default=sa.text('now()'), nullable=False, comment='更新时间'),
        sa.Column('update_by', sa.BigInteger(), nullable=True, comment='更新人'),
        sa.Column('version', sa.Integer(), nullable=True, comment='乐观锁版本'),
        sa.Column('deleted', sa.Integer(), nullable=True, comment='逻辑删除 0/1'),
        sa.ForeignKeyConstraint(['instance_id'], ['approval_instance.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'instance_id', name='uq_approval_view_state_user_instance')
    )
    op.create_index(op.f('ix_approval_view_state_instance_id'), 'approval_view_state', ['instance_id'], unique=False)
    op.create_index(op.f('ix_approval_view_state_user_id'), 'approval_view_state', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('approval_view_state')
    op.drop_table('approval_cc')
    op.drop_column('approval_record', 'payload')
    op.drop_column('approval_task', 'action_meta')
    op.drop_column('approval_task', 'node_type')
    op.drop_column('approval_instance', 'variables')
    op.drop_column('approval_instance', 'current_node_ids')
    op.drop_column('approval_node', 'default_seq')
    op.drop_column('approval_node', 'branches')
    op.drop_column('approval_node', 'sign_mode')
    op.drop_column('approval_node', 'node_type')
    op.drop_column('approval_definition', 'variables_schema')
    op.drop_column('approval_definition', 'process_graph')
