"""org membership (sys_user_dept) + approval_node.chain_levels

- 新增用户-部门任职表 sys_user_dept（user_id/dept_id/is_primary/is_leader，user+dept 唯一）；
- 回填：既有 sys_user.dept_id 灌为 is_primary=1 任职（user.dept_id 保留为主部门冗余）；
- approval_node 增加 chain_levels（SUPERVISOR_CHAIN 逐级级数）。

Revision ID: f7a8b9c0d1e2
Revises: d5e6f7a8b9c0
Create Date: 2026-10-24
"""
import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "d5e6f7a8b9c0"
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
        "sys_user_dept",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("dept_id", sa.BigInteger(), nullable=False),
        sa.Column("is_primary", sa.Integer(), nullable=False, server_default="0", comment="主部门标记"),
        sa.Column("is_leader", sa.Integer(), nullable=False, server_default="0", comment="部门负责人标记"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "dept_id", name="uq_sys_user_dept_user_dept"),
    )
    op.create_index("ix_sys_user_dept_user_id", "sys_user_dept", ["user_id"])
    op.create_index("ix_sys_user_dept_dept_id", "sys_user_dept", ["dept_id"])
    # 回填：既有 user.dept_id → 主部门任职（NOT EXISTS 保证可重复执行不重复插入）
    op.execute(
        """
        INSERT INTO sys_user_dept (user_id, dept_id, is_primary, is_leader, create_time, update_time)
        SELECT u.id, u.dept_id, 1, 0, now(), now()
        FROM sys_user u
        WHERE u.dept_id IS NOT NULL AND (u.deleted = 0 OR u.deleted IS NULL)
          AND NOT EXISTS (
              SELECT 1 FROM sys_user_dept m WHERE m.user_id = u.id AND m.dept_id = u.dept_id
          )
        """
    )
    op.add_column(
        "approval_node",
        sa.Column("chain_levels", sa.Integer(), nullable=True, comment="SUPERVISOR_CHAIN 逐级级数（空/0=到根）"),
    )
    # PARENT_DEPT_LEADER(18) 超过原 varchar(16)
    op.alter_column("approval_node", "approver_type", type_=sa.String(32), existing_nullable=False)


def downgrade() -> None:
    op.drop_column("approval_node", "chain_levels")
    op.drop_index("ix_sys_user_dept_dept_id", table_name="sys_user_dept")
    op.drop_index("ix_sys_user_dept_user_id", table_name="sys_user_dept")
    op.drop_table("sys_user_dept")
