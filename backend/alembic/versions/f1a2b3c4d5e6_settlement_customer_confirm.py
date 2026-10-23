"""fin_settlement 客户确认列 + fin_settlement_confirm 留痕表

2026-10-21 迭代评审：结算单审批通过后须"发送客户确认"，客户确认（一期内部代客标记）
后才允许申请开票；发送/确认/异议全程留痕。

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-10-27
"""
import sqlalchemy as sa

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fin_settlement",
        sa.Column("confirm_status", sa.String(16), nullable=False, server_default="", comment="客户确认状态"),
    )
    op.add_column(
        "fin_settlement",
        sa.Column("confirm_by", sa.BigInteger(), nullable=True, comment="代客确认操作人"),
    )
    op.add_column(
        "fin_settlement",
        sa.Column("confirm_time", sa.DateTime(), nullable=True, comment="确认时间"),
    )
    op.add_column(
        "fin_settlement",
        sa.Column("confirm_note", sa.String(255), nullable=False, server_default="", comment="确认说明"),
    )
    op.create_index("ix_fin_settlement_confirm_status", "fin_settlement", ["confirm_status"])

    op.create_table(
        "fin_settlement_confirm",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True, comment="主键"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.func.now(), comment="创建时间"),
        sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.func.now(), comment="更新时间"),
        sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
        sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
        sa.Column("settlement_id", sa.BigInteger(), nullable=False, comment="fin_settlement.id"),
        sa.Column("action", sa.String(16), nullable=False, comment="send/confirm/object"),
        sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人"),
        sa.Column("operator_name", sa.String(64), nullable=False, server_default="", comment="操作人姓名冗余"),
        sa.Column("receiver_id", sa.BigInteger(), nullable=True, comment="站内通知收件人（send 时）"),
        sa.Column("receiver_name", sa.String(64), nullable=False, server_default="", comment="收件人姓名冗余"),
        sa.Column("note", sa.String(500), nullable=False, server_default="", comment="说明"),
    )
    op.create_index("ix_fin_settlement_confirm_settlement_id", "fin_settlement_confirm", ["settlement_id"])


def downgrade() -> None:
    op.drop_table("fin_settlement_confirm")
    op.drop_index("ix_fin_settlement_confirm_status", table_name="fin_settlement")
    op.drop_column("fin_settlement", "confirm_note")
    op.drop_column("fin_settlement", "confirm_time")
    op.drop_column("fin_settlement", "confirm_by")
    op.drop_column("fin_settlement", "confirm_status")
