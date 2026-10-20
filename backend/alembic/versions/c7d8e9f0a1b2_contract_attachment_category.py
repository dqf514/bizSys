"""ctr_contract_attachment.category（合同电子版 econtract / 其他附件 other）

存量附件一律归为 other（开发阶段无存量包袱）。

Revision ID: c7d8e9f0a1b2
Revises: b8c9d0e1f2a3
Create Date: 2026-10-24
"""
import sqlalchemy as sa

from alembic import op

revision = "c7d8e9f0a1b2"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ctr_contract_attachment",
        sa.Column(
            "category",
            sa.String(32),
            nullable=False,
            server_default="other",
            comment="附件分类：econtract 合同电子版 / other 其他附件",
        ),
    )


def downgrade() -> None:
    op.drop_column("ctr_contract_attachment", "category")
