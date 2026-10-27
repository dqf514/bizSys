"""procurement phase-2：招投标（pur_tender 系列）+ 合作方门户账号（partner_user）

- 新建 pur_tender / pur_tender_registration / pur_tender_bid / pur_tender_eval；
- 新建 partner_user（门户独立账号体系，注册审核制，可绑定 crm_customer）。

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
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
        "pur_tender",
        sa.Column("tender_no", sa.String(32), nullable=True, comment="招标编号 ZB...（发布时发放，draft 为空）"),
        sa.Column("name", sa.String(255), nullable=False, comment="项目名称"),
        sa.Column("request_id", sa.BigInteger(), nullable=True, comment="关联采购申请"),
        sa.Column("request_no", sa.String(32), nullable=False, server_default="", comment="申请编号冗余"),
        sa.Column("tender_method", sa.String(16), nullable=False, server_default="public", comment="字典 tender_method"),
        sa.Column("budget_amount", sa.Numeric(14, 2), nullable=True, comment="预算金额"),
        sa.Column("reg_deadline", sa.DateTime(), nullable=True, comment="报名截止时间"),
        sa.Column("bid_deadline", sa.DateTime(), nullable=True, comment="投标截止时间"),
        sa.Column("open_time", sa.DateTime(), nullable=True, comment="开标时间"),
        sa.Column("announcement", sa.Text(), nullable=True, comment="公告内容"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("award_bid_id", sa.BigInteger(), nullable=True, comment="定标审批中的投标"),
        sa.Column("winner_bid_id", sa.BigInteger(), nullable=True, comment="中标投标"),
        sa.Column("winner_name", sa.String(255), nullable=False, server_default="", comment="中标单位冗余（公示口径）"),
        sa.Column("winner_amount", sa.Numeric(14, 2), nullable=True, comment="中标价（公示口径）"),
        sa.Column("contract_id", sa.BigInteger(), nullable=True, comment="定标生成的采购合同（幂等）"),
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tender_no"),
    )
    op.create_index("ix_pur_tender_tender_no", "pur_tender", ["tender_no"])
    op.create_index("ix_pur_tender_name", "pur_tender", ["name"])
    op.create_index("ix_pur_tender_request_id", "pur_tender", ["request_id"])
    op.create_index("ix_pur_tender_status", "pur_tender", ["status"])
    op.create_index("ix_pur_tender_flow_instance_id", "pur_tender", ["flow_instance_id"])

    op.create_table(
        "pur_tender_registration",
        sa.Column("tender_id", sa.BigInteger(), nullable=False),
        sa.Column("partner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("contact_phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("qualification_path", sa.String(255), nullable=False, server_default=""),
        sa.Column("qualification_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("review_by", sa.BigInteger(), nullable=True),
        sa.Column("review_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("review_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.String(500), nullable=False, server_default=""),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tender_id"], ["pur_tender.id"]),
    )
    op.create_index("ix_pur_tender_registration_tender_id", "pur_tender_registration", ["tender_id"])
    op.create_index("ix_pur_tender_registration_partner_user_id", "pur_tender_registration", ["partner_user_id"])
    op.create_index("ix_pur_tender_registration_status", "pur_tender_registration", ["status"])

    op.create_table(
        "pur_tender_bid",
        sa.Column("tender_id", sa.BigInteger(), nullable=False),
        sa.Column("partner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("registration_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("company_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("price", sa.Numeric(14, 2), nullable=False, comment="报价"),
        sa.Column("proposal_path", sa.String(255), nullable=False, server_default=""),
        sa.Column("proposal_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("comment", sa.Text(), nullable=True, comment="投标说明"),
        sa.Column("submit_at", sa.DateTime(), nullable=True, comment="最近提交时间"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tender_id"], ["pur_tender.id"]),
    )
    op.create_index("ix_pur_tender_bid_tender_id", "pur_tender_bid", ["tender_id"])
    op.create_index("ix_pur_tender_bid_partner_user_id", "pur_tender_bid", ["partner_user_id"])

    op.create_table(
        "pur_tender_eval",
        sa.Column("tender_id", sa.BigInteger(), nullable=False),
        sa.Column("bid_id", sa.BigInteger(), nullable=False),
        sa.Column("evaluator_id", sa.BigInteger(), nullable=False),
        sa.Column("evaluator_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("score", sa.Numeric(5, 1), nullable=False, comment="评分 0-100"),
        sa.Column("comment", sa.String(500), nullable=False, server_default="", comment="评语"),
        sa.Column("recommend", sa.Integer(), nullable=False, server_default="0", comment="推荐中标 0/1"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tender_id"], ["pur_tender.id"]),
        sa.ForeignKeyConstraint(["bid_id"], ["pur_tender_bid.id"]),
    )
    op.create_index("ix_pur_tender_eval_tender_id", "pur_tender_eval", ["tender_id"])
    op.create_index("ix_pur_tender_eval_bid_id", "pur_tender_eval", ["bid_id"])
    op.create_index("ix_pur_tender_eval_evaluator_id", "pur_tender_eval", ["evaluator_id"])

    op.create_table(
        "partner_user",
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False, comment="公司名"),
        sa.Column("contact_name", sa.String(64), nullable=False, server_default="", comment="联系人"),
        sa.Column("phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("email", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("customer_id", sa.BigInteger(), nullable=True, comment="绑定往来单位 crm_customer.id"),
        sa.Column("review_by", sa.BigInteger(), nullable=True),
        sa.Column("review_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("review_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.String(500), nullable=False, server_default=""),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
    )
    op.create_index("ix_partner_user_username", "partner_user", ["username"])
    op.create_index("ix_partner_user_company_name", "partner_user", ["company_name"])
    op.create_index("ix_partner_user_status", "partner_user", ["status"])
    op.create_index("ix_partner_user_customer_id", "partner_user", ["customer_id"])


def downgrade() -> None:
    op.drop_table("partner_user")
    op.drop_table("pur_tender_eval")
    op.drop_table("pur_tender_bid")
    op.drop_table("pur_tender_registration")
    op.drop_table("pur_tender")
