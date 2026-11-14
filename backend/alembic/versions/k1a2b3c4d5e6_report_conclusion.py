"""报告 conclusion 字段（AI 全文辅助：结论与不确定度段人工采用后落库）

Revision ID: k1a2b3c4d5e6
Revises: j1a2b3c4d5e6
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "k1a2b3c4d5e6"
down_revision = "j1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "rpt_report",
        sa.Column("conclusion", sa.Text(), nullable=True, comment="结论与不确定度段（AI 草稿人工采用后落库）"),
    )


def downgrade() -> None:
    op.drop_column("rpt_report", "conclusion")
