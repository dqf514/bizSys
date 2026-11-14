"""AI-5：ai_usage_log 加脱敏级别 masking + 估算成本 cost 列

Revision ID: m1a2b3c4d5e6
Revises: l1a2b3c4d5e6
Create Date: 2026-11-24
"""
import sqlalchemy as sa
from alembic import op

revision = "m1a2b3c4d5e6"
down_revision = "l1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_usage_log",
        sa.Column("masking", sa.String(8), nullable=False, server_default="", comment="实际生效脱敏级别 off/standard/strict"),
    )
    op.add_column(
        "ai_usage_log",
        sa.Column("cost", sa.Numeric(12, 6), nullable=True, comment="按当时单价估算的成本（无单价为 null）"),
    )


def downgrade() -> None:
    op.drop_column("ai_usage_log", "cost")
    op.drop_column("ai_usage_log", "masking")
