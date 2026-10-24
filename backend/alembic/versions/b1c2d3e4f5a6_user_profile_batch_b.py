"""批次B 个人档案：sys_user 组织/头像列 + 紧急联系人/银行卡表

- sys_user 增加 employee_no（工号）/ hire_date（入职日期）/ job_level（职级，预留对接 HR）/ avatar（头像相对路径）；
- 新增 user_emergency_contact（紧急联系人，多条）、user_bank_account（银行卡，多条，接口默认脱敏）。

Revision ID: b1c2d3e4f5a6
Revises: f1a2b3c4d5e6
Create Date: 2026-10-24
"""
import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "f1a2b3c4d5e6"
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
    op.add_column(
        "sys_user",
        sa.Column("employee_no", sa.String(32), nullable=False, server_default="", comment="工号（组织统一管理）"),
    )
    op.add_column("sys_user", sa.Column("hire_date", sa.Date(), nullable=True, comment="入职日期"))
    op.add_column(
        "sys_user",
        sa.Column("job_level", sa.String(32), nullable=False, server_default="", comment="职级（预留，对接 HR）"),
    )
    op.add_column(
        "sys_user",
        sa.Column("avatar", sa.String(255), nullable=False, server_default="", comment="头像文件相对路径"),
    )

    op.create_table(
        "user_emergency_contact",
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="所属用户"),
        sa.Column("name", sa.String(64), nullable=False, comment="姓名"),
        sa.Column("relation", sa.String(32), nullable=False, server_default="", comment="关系"),
        sa.Column("phone", sa.String(32), nullable=False, server_default="", comment="电话"),
        sa.Column("remark", sa.String(255), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_emergency_contact_user_id", "user_emergency_contact", ["user_id"])

    op.create_table(
        "user_bank_account",
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="所属用户"),
        sa.Column("bank_name", sa.String(64), nullable=False, comment="开户行"),
        sa.Column("card_no", sa.String(32), nullable=False, comment="卡号"),
        sa.Column("holder_name", sa.String(64), nullable=False, server_default="", comment="持卡人"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_bank_account_user_id", "user_bank_account", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_bank_account_user_id", table_name="user_bank_account")
    op.drop_table("user_bank_account")
    op.drop_index("ix_user_emergency_contact_user_id", table_name="user_emergency_contact")
    op.drop_table("user_emergency_contact")
    op.drop_column("sys_user", "avatar")
    op.drop_column("sys_user", "job_level")
    op.drop_column("sys_user", "hire_date")
    op.drop_column("sys_user", "employee_no")
