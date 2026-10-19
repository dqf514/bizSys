"""oa tables (oa_form / oa_instance)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-10-19
"""
import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None

_BASE_COLS = [
    sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
    sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="创建时间"),
    sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
    sa.Column("update_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="更新时间"),
    sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
    sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
    sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
]


def upgrade() -> None:
    op.create_table(
        "oa_form",
        sa.Column("key", sa.String(length=64), nullable=False, comment="表单标识"),
        sa.Column("name", sa.String(length=128), nullable=False, comment="表单名称"),
        sa.Column("form_version", sa.Integer(), nullable=False, comment="表单版本（version 列是乐观锁）"),
        sa.Column("status", sa.String(length=16), nullable=False, comment="draft/published/disabled"),
        sa.Column("category", sa.String(length=32), nullable=False, comment="分类（字典 oa_category）"),
        sa.Column("icon", sa.String(length=64), nullable=False),
        sa.Column("sort", sa.Integer(), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=True, comment="字段定义 JSON"),
        sa.Column("flow_definition_id", sa.BigInteger(), nullable=True, comment="绑定 approval_definition.id；空=直通"),
        sa.Column("description", sa.String(length=512), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", "form_version", "deleted", name="uq_oa_form_key_version"),
    )
    op.create_index("ix_oa_form_key", "oa_form", ["key"])
    op.create_index("ix_oa_form_status", "oa_form", ["status"])
    op.create_index("ix_oa_form_category", "oa_form", ["category"])

    op.create_table(
        "oa_instance",
        sa.Column("display_no", sa.String(length=32), nullable=False, comment="OA 编号（biz_type=oa 发号）"),
        sa.Column("form_id", sa.BigInteger(), nullable=False),
        sa.Column("form_key", sa.String(length=64), nullable=False),
        sa.Column("form_name", sa.String(length=128), nullable=False),
        sa.Column("form_version", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("schema_json", sa.Text(), nullable=True, comment="提交时表单结构快照"),
        sa.Column("applicant_id", sa.BigInteger(), nullable=False),
        sa.Column("applicant_name", sa.String(length=64), nullable=False),
        sa.Column("form_data", sa.Text(), nullable=True, comment="表单数据 JSON"),
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="approval_instance.id；直通为 NULL"),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            comment="running/approved/rejected/withdrawn/terminated",
        ),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oa_instance_display_no", "oa_instance", ["display_no"])
    op.create_index("ix_oa_instance_form_id", "oa_instance", ["form_id"])
    op.create_index("ix_oa_instance_category", "oa_instance", ["category"])
    op.create_index("ix_oa_instance_applicant_id", "oa_instance", ["applicant_id"])
    op.create_index("ix_oa_instance_flow_instance_id", "oa_instance", ["flow_instance_id"])
    op.create_index("ix_oa_instance_status", "oa_instance", ["status"])


def downgrade() -> None:
    op.drop_table("oa_instance")
    op.drop_table("oa_form")
