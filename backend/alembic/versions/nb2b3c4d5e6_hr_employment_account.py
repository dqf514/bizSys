"""HR L1：人事事务单的「开账号」字段（B10-1 S4）

入职单需要记住「要开系统账号 + 用什么登录名 / 初始密码 / 绑哪些角色」，
否则审批通过后（`approved`）再点「生效」时表单已经不在手上，无从建号。

`hr_employment` 补 4 列：
- `create_account`：生效时是否创建系统账号；
- `account_username`：登录名（留空则用工号）；
- `account_password`：**AES-GCM 密文**（`enc:` 前缀，域 `hr-account-password`），
  不落明文；
- `account_roles`：逗号分隔的角色 id。

手工迁移：`alembic/env.py` 未 import hr 域 models，autogenerate 会试图删表。

Revision ID: nb2b3c4d5e6
Revises: na2b3c4d5e6
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op

revision = "nb2b3c4d5e6"
down_revision = "na2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "hr_employment",
        sa.Column(
            "create_account",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="生效时是否创建系统账号 0/1",
        ),
    )
    op.add_column(
        "hr_employment",
        sa.Column(
            "account_username",
            sa.String(64),
            nullable=False,
            server_default="",
            comment="账号登录名（留空则用工号）",
        ),
    )
    op.add_column(
        "hr_employment",
        sa.Column(
            "account_password",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="初始密码（AES-GCM 密文 enc: 前缀）",
        ),
    )
    op.add_column(
        "hr_employment",
        sa.Column(
            "account_roles",
            sa.String(255),
            nullable=False,
            server_default="",
            comment="逗号分隔的角色 id",
        ),
    )


def downgrade() -> None:
    op.drop_column("hr_employment", "account_roles")
    op.drop_column("hr_employment", "account_password")
    op.drop_column("hr_employment", "account_username")
    op.drop_column("hr_employment", "create_account")
