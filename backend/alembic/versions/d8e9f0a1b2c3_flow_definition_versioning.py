"""approval_definition 版本化：flow_version + 联合唯一 (code, flow_version, deleted)

- 原 code 单列唯一约束替换为 (code, flow_version, deleted) 联合唯一；
- 存量定义 flow_version=1；enabled 列继续承担启用/停用语义。

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-24
"""
import sqlalchemy as sa

from alembic import op

revision = "d8e9f0a1b2c3"
down_revision = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_definition",
        sa.Column(
            "flow_version",
            sa.Integer(),
            nullable=False,
            server_default="1",
            comment="定义版本号（同 code 递增，从 1 起）",
        ),
    )
    op.drop_constraint("code", "approval_definition", type_="unique")
    op.create_unique_constraint(
        "uq_approval_definition_code_version",
        "approval_definition",
        ["code", "flow_version", "deleted"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_approval_definition_code_version", "approval_definition", type_="unique")
    op.create_unique_constraint("code", "approval_definition", ["code"])
    op.drop_column("approval_definition", "flow_version")
