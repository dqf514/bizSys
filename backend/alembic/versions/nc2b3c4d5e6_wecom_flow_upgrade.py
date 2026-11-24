"""E1 企业微信审批移植：流程通用选项 + 节点字段权限

- `approval_definition.options`：流程级通用选项 JSON（意见必填 / 意见需签名 / 允许加签 /
  通过后可撤销 / 审批人可改流程 / 可改抄送 / 办理意见必填 / 办理人可修改 / 允许代提交 /
  明细表权限控制）。未配置 = 保持既有行为。
- `approval_node.field_permissions`：节点级字段权限 JSON `{字段key: editable|viewonly|hidden}`
  （对应企业微信的「仅可见 / 可编辑」）。

手工迁移：approval 域虽在 `alembic/env.py` 的 import 列表里，但按仓库惯例仍手写，
避免 autogenerate 把非 metadata 表的变更算成删表。

Revision ID: nc2b3c4d5e6
Revises: nb2b3c4d5e6
Create Date: 2026-11-24
"""

import sqlalchemy as sa
from alembic import op

revision = "nc2b3c4d5e6"
down_revision = "nb2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_definition",
        sa.Column(
            "options",
            sa.Text(),
            nullable=True,
            comment="流程通用选项 JSON（意见必填/允许加签/通过后可撤销/办理人可修改…）",
        ),
    )
    op.add_column(
        "approval_node",
        sa.Column(
            "field_permissions",
            sa.Text(),
            nullable=True,
            comment="节点字段权限 JSON：{字段key: editable|viewonly|hidden}",
        ),
    )


def downgrade() -> None:
    op.drop_column("approval_node", "field_permissions")
    op.drop_column("approval_definition", "options")
