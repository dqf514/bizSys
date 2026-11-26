"""B12 文档中心改微盘式：空间支持置顶

`kb_space` 新增 `pinned` 列（1 = 置顶），供文档中心左栏「置顶」分组使用。

Revision ID: nf2b3c4d5e6
Revises: ne2b3c4d5e6
Create Date: 2026-11-26
"""

import sqlalchemy as sa
from alembic import op

revision = "nf2b3c4d5e6"
down_revision = "ne2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "kb_space",
        sa.Column("pinned", sa.Integer(), nullable=False, server_default="0", comment="是否置顶"),
    )
    op.create_index("ix_kb_space_pinned", "kb_space", ["pinned"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_kb_space_pinned", table_name="kb_space")
    op.drop_column("kb_space", "pinned")
