"""登录安全升级：sys_user 增加 mfa_enabled（二步验证开关）

Revision ID: g1a2b3c4d5e6
Revises: a1b2c3d4e5f7
Create Date: 2026-11-10
"""
import sqlalchemy as sa

from alembic import op

revision = "g1a2b3c4d5e6"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sys_user",
        sa.Column("mfa_enabled", sa.Integer(), nullable=False, server_default="0", comment="二步验证（MFA）开关 0/1"),
    )


def downgrade() -> None:
    op.drop_column("sys_user", "mfa_enabled")
