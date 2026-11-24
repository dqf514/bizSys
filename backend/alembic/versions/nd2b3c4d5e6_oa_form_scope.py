"""E1 企业微信审批移植：OA 表单可见范围

- `oa_form.scope_json`：模板可见范围 JSON `{"depts":[...], "roles":[...], "users":[...]}`；
  空 = 全员可见。对应企业微信审批模板的「可见范围：部门 / 人员名单 / 全公司」。

手工迁移：oa 域不在 `alembic/env.py` 的 import 列表里，autogenerate 会试图删表，必须手写。

Revision ID: nd2b3c4d5e6
Revises: nc2b3c4d5e6
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from alembic import op

revision = "nd2b3c4d5e6"
down_revision = "nc2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "oa_form",
        sa.Column(
            "scope_json",
            sa.Text(),
            nullable=True,
            comment="模板可见范围 JSON：{depts:[],roles:[],users:[]}（空=全员可见）",
        ),
    )


def downgrade() -> None:
    op.drop_column("oa_form", "scope_json")
