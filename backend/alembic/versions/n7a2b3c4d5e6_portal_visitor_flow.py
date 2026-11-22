"""F6 门户访客预约闭环：vis_visit 挂审批引擎实例 + 门户提交账号

- `vis_visit.flow_instance_id`：访客单接入通用审批引擎后的实例 id；
- `vis_visit.partner_user_id`：提交预约的门户合作方账号 id（门户数据隔离口径）。

手写迁移（`alembic/env.py` 未 import visitor/models，autogenerate 会试图删表）。

Revision ID: n7a2b3c4d5e6
Revises: n6a2b3c4d5e6
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

revision = "n7a2b3c4d5e6"
down_revision = "n6a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "vis_visit",
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="审批引擎实例 id"),
    )
    op.create_index("ix_vis_visit_flow_instance_id", "vis_visit", ["flow_instance_id"])
    op.add_column(
        "vis_visit",
        sa.Column("partner_user_id", sa.BigInteger(), nullable=True, comment="提交预约的门户合作方账号 id"),
    )
    op.create_index("ix_vis_visit_partner_user_id", "vis_visit", ["partner_user_id"])


def downgrade() -> None:
    op.drop_index("ix_vis_visit_partner_user_id", table_name="vis_visit")
    op.drop_column("vis_visit", "partner_user_id")
    op.drop_index("ix_vis_visit_flow_instance_id", table_name="vis_visit")
    op.drop_column("vis_visit", "flow_instance_id")
