"""往来单位详情增强：crm_partner_contact + crm_partner_attachment

- crm_partner_contact：联系人（姓名/职务/电话/邮箱/主要联系人/备注），is_primary 应用层保证每单位唯一；
- crm_partner_attachment：附件集中管理（分类字典 partner_attachment_category、文件路径/大小/说明）。

Revision ID: a1b2c3d4e5f7
Revises: e3f4a5b6c7d8
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "e3f4a5b6c7d8"
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
        "crm_partner_contact",
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="往来单位 crm_customer.id"),
        sa.Column("name", sa.String(64), nullable=False, comment="姓名"),
        sa.Column("position", sa.String(64), nullable=False, server_default="", comment="职务"),
        sa.Column("phone", sa.String(32), nullable=False, server_default="", comment="电话"),
        sa.Column("email", sa.String(128), nullable=False, server_default="", comment="邮箱"),
        sa.Column("is_primary", sa.Integer(), nullable=False, server_default="0", comment="主要联系人 0/1"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customer.id"]),
    )
    op.create_index("ix_crm_partner_contact_customer_id", "crm_partner_contact", ["customer_id"])

    op.create_table(
        "crm_partner_attachment",
        sa.Column("customer_id", sa.BigInteger(), nullable=False, comment="往来单位 crm_customer.id"),
        sa.Column("category", sa.String(32), nullable=False, server_default="other",
                  comment="字典 partner_attachment_category"),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("path", sa.String(255), nullable=False, comment="相对 upload_dir 的路径"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="说明"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["customer_id"], ["crm_customer.id"]),
    )
    op.create_index("ix_crm_partner_attachment_customer_id", "crm_partner_attachment", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_crm_partner_attachment_customer_id", table_name="crm_partner_attachment")
    op.drop_table("crm_partner_attachment")
    op.drop_index("ix_crm_partner_contact_customer_id", table_name="crm_partner_contact")
    op.drop_table("crm_partner_contact")
