"""B2 客户自助体系：在线任务委托（task_entrust / task_entrust_item）+ 客户方人员备案（crm_partner_staff）
+ 门户账号扩展（partner_user 账号类型 / 权限范围 / 客户经理 / 人员名额上限）

Revision ID: n2a2b3c4d5e6
Revises: n1a2b3c4d5e6
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "n2a2b3c4d5e6"
down_revision = "n1a2b3c4d5e6"
branch_labels = None
depends_on = None


def _base_cols() -> list:
    return [
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="创建时间"),
        sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="更新时间"),
        sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
        sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
    ]


def _create(table: str, cols: list, indexes: list | None = None, fks: list | None = None) -> None:
    op.create_table(
        table,
        *_base_cols(),
        *cols,
        *(
            [
                sa.ForeignKeyConstraint(
                    [fk["column"]], [fk["target"]], name=fk["name"], ondelete=fk.get("ondelete")
                )
                for fk in (fks or [])
            ]
        ),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    for idx in indexes or []:
        op.create_index(idx["name"], table, idx["cols"], unique=idx.get("unique", False))


def upgrade() -> None:
    # ---------------- 在线任务委托单 ----------------
    _create(
        "task_entrust",
        [
            sa.Column("entrust_no", sa.String(32), nullable=True, comment="委托单号 WT...（受理时发放）"),
            sa.Column("title", sa.String(255), nullable=False, comment="委托标题"),
            sa.Column("entrust_type", sa.String(32), nullable=True, comment="字典 entrust_type：sim/model/test/outsource"),
            sa.Column("contract_id", sa.BigInteger(), nullable=True, comment="关联合同 ctr_contract.id"),
            sa.Column("contract_no", sa.String(32), nullable=True, comment="合同号冗余"),
            sa.Column("customer_id", sa.BigInteger(), nullable=True, comment="客户 crm_customer.id"),
            sa.Column("customer_name", sa.String(128), nullable=True, comment="客户名冗余"),
            sa.Column("biz_block", sa.String(32), nullable=True, comment="字典 biz_block"),
            sa.Column("source", sa.String(16), nullable=True, comment="portal 客户自助 / staff 业务代提交"),
            sa.Column("applicant_type", sa.String(16), nullable=True, comment="portal 客户 / internal 员工"),
            sa.Column("applicant_id", sa.BigInteger(), nullable=True, comment="申请人 id"),
            sa.Column("applicant_name", sa.String(64), nullable=True, comment="申请人姓名"),
            sa.Column("applicant_phone", sa.String(32), nullable=True, comment="申请人电话"),
            sa.Column("requirement", sa.Text(), nullable=True, comment="技术要求 / 需求描述"),
            sa.Column("sample_desc", sa.String(500), nullable=True, comment="送样 / 样车说明"),
            sa.Column("plan_start_date", sa.Date(), nullable=True, comment="计划开始日期"),
            sa.Column("plan_end_date", sa.Date(), nullable=True, comment="期望完成日期"),
            sa.Column("priority", sa.String(16), nullable=True, comment="normal / urgent"),
            sa.Column("amount", sa.Numeric(14, 2), nullable=True, comment="预估金额"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/submitted/accepted/rejected/dispatched/closed/cancelled"),
            sa.Column("handler_id", sa.BigInteger(), nullable=True, comment="受理人（客户经理）"),
            sa.Column("handler_name", sa.String(64), nullable=True, comment="受理人姓名"),
            sa.Column("biz_owner_id", sa.BigInteger(), nullable=True, comment="业务负责人（受理后抄送）"),
            sa.Column("biz_owner_name", sa.String(64), nullable=True, comment="业务负责人姓名"),
            sa.Column("review_by", sa.BigInteger(), nullable=True, comment="审核人"),
            sa.Column("review_name", sa.String(64), nullable=True, comment="审核人姓名"),
            sa.Column("review_at", sa.DateTime(), nullable=True, comment="审核时间"),
            sa.Column("review_comment", sa.String(500), nullable=True, comment="审核意见"),
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment="生成的任务 task_task.id"),
            sa.Column("task_no", sa.String(32), nullable=True, comment="任务编号冗余"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_task_entrust_entrust_no", "cols": ["entrust_no"], "unique": True},
            {"name": "ix_task_entrust_title", "cols": ["title"]},
            {"name": "ix_task_entrust_entrust_type", "cols": ["entrust_type"]},
            {"name": "ix_task_entrust_contract_id", "cols": ["contract_id"]},
            {"name": "ix_task_entrust_customer_id", "cols": ["customer_id"]},
            {"name": "ix_task_entrust_customer_name", "cols": ["customer_name"]},
            {"name": "ix_task_entrust_biz_block", "cols": ["biz_block"]},
            {"name": "ix_task_entrust_source", "cols": ["source"]},
            {"name": "ix_task_entrust_applicant_id", "cols": ["applicant_id"]},
            {"name": "ix_task_entrust_status", "cols": ["status"]},
            {"name": "ix_task_entrust_handler_id", "cols": ["handler_id"]},
            {"name": "ix_task_entrust_biz_owner_id", "cols": ["biz_owner_id"]},
            {"name": "ix_task_entrust_task_id", "cols": ["task_id"]},
        ],
    )
    _create(
        "task_entrust_item",
        [
            sa.Column("entrust_id", sa.BigInteger(), nullable=False, comment="所属委托 task_entrust.id"),
            sa.Column("item_code", sa.String(32), nullable=True, comment="条目编号"),
            sa.Column("name", sa.String(128), nullable=True, comment="试验项目"),
            sa.Column("std", sa.String(128), nullable=True, comment="依据标准"),
            sa.Column("qty", sa.Integer(), nullable=True, comment="数量 / 台次"),
            sa.Column("need_report", sa.Integer(), nullable=True, comment="是否出报告 0/1"),
            sa.Column("report_type", sa.String(32), nullable=True, comment="报告类型"),
            sa.Column("remark", sa.String(255), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_task_entrust_item_entrust_id", "cols": ["entrust_id"]},
        ],
        fks=[
            {
                "column": "entrust_id",
                "target": "task_entrust.id",
                "name": "fk_task_entrust_item_entrust",
            }
        ],
    )

    # ---------------- 客户方人员备案 ----------------
    _create(
        "crm_partner_staff",
        [
            sa.Column("customer_id", sa.BigInteger(), nullable=True, comment="客户 crm_customer.id"),
            sa.Column("customer_name", sa.String(128), nullable=True, comment="客户名冗余"),
            sa.Column("name", sa.String(64), nullable=False, comment="姓名"),
            sa.Column("gender", sa.String(8), nullable=True, comment="性别"),
            sa.Column("id_no", sa.String(64), nullable=True, comment="证件号"),
            sa.Column("position", sa.String(64), nullable=True, comment="职务"),
            sa.Column("phone", sa.String(32), nullable=True, comment="电话"),
            sa.Column("email", sa.String(128), nullable=True, comment="邮箱"),
            sa.Column("plate_no", sa.String(32), nullable=True, comment="车牌号"),
            sa.Column("company", sa.String(255), nullable=True, comment="所属单位"),
            sa.Column("staff_type", sa.String(32), nullable=True, comment="字典 partner_staff_type"),
            sa.Column("visit_purpose", sa.String(255), nullable=True, comment="来访事由"),
            sa.Column("plan_visit_date", sa.Date(), nullable=True, comment="计划来访日期"),
            sa.Column("nda_signed", sa.Integer(), nullable=True, comment="是否已签 NDA 0/1"),
            sa.Column("visit_perm", sa.String(255), nullable=True, comment="可进入区域 id 列表"),
            sa.Column("source", sa.String(16), nullable=True, comment="portal 客户自助 / internal 代登记"),
            sa.Column("applicant_account_id", sa.BigInteger(), nullable=True, comment="登记账号 partner_user.id"),
            sa.Column("applicant_name", sa.String(64), nullable=True, comment="登记人"),
            sa.Column("status", sa.String(16), nullable=True, comment="pending/approved/rejected/disabled"),
            sa.Column("review_by", sa.BigInteger(), nullable=True, comment="审核人"),
            sa.Column("review_name", sa.String(64), nullable=True, comment="审核人姓名"),
            sa.Column("review_at", sa.DateTime(), nullable=True, comment="审核时间"),
            sa.Column("review_comment", sa.String(500), nullable=True, comment="审核意见"),
            sa.Column("biz_owner_id", sa.BigInteger(), nullable=True, comment="业务负责人（审核后抄送）"),
            sa.Column("biz_owner_name", sa.String(64), nullable=True, comment="业务负责人姓名"),
            sa.Column("notify_visitor_admin", sa.Integer(), nullable=True, comment="是否抄送访客管理人员"),
            sa.Column("visitor_id", sa.BigInteger(), nullable=True, comment="访客档案 id（B3 预登记）"),
            sa.Column("remark", sa.String(500), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_crm_partner_staff_customer_id", "cols": ["customer_id"]},
            {"name": "ix_crm_partner_staff_customer_name", "cols": ["customer_name"]},
            {"name": "ix_crm_partner_staff_name", "cols": ["name"]},
            {"name": "ix_crm_partner_staff_phone", "cols": ["phone"]},
            {"name": "ix_crm_partner_staff_staff_type", "cols": ["staff_type"]},
            {"name": "ix_crm_partner_staff_source", "cols": ["source"]},
            {"name": "ix_crm_partner_staff_applicant_account_id", "cols": ["applicant_account_id"]},
            {"name": "ix_crm_partner_staff_status", "cols": ["status"]},
            {"name": "ix_crm_partner_staff_biz_owner_id", "cols": ["biz_owner_id"]},
            {"name": "ix_crm_partner_staff_visitor_id", "cols": ["visitor_id"]},
        ],
    )

    # ---------------- 门户账号扩展（客户自助账号） ----------------
    op.add_column(
        "partner_user",
        sa.Column("account_type", sa.String(16), nullable=True, server_default="supplier", comment="customer/supplier"),
    )
    op.add_column(
        "partner_user",
        sa.Column(
            "perm_scope",
            sa.String(64),
            nullable=True,
            server_default="tender",
            comment="权限范围：tender/entrust/staff",
        ),
    )
    op.add_column(
        "partner_user",
        sa.Column("manager_id", sa.BigInteger(), nullable=True, comment="归属客户经理 sys_user.id"),
    )
    op.add_column(
        "partner_user",
        sa.Column("manager_name", sa.String(64), nullable=True, comment="归属客户经理姓名"),
    )
    op.add_column(
        "partner_user",
        sa.Column("staff_limit", sa.Integer(), nullable=True, server_default="5", comment="可登记外来人员名额上限"),
    )
    op.create_index("ix_partner_user_account_type", "partner_user", ["account_type"])
    op.create_index("ix_partner_user_manager_id", "partner_user", ["manager_id"])


def downgrade() -> None:
    op.drop_index("ix_partner_user_manager_id", table_name="partner_user")
    op.drop_index("ix_partner_user_account_type", table_name="partner_user")
    op.drop_column("partner_user", "staff_limit")
    op.drop_column("partner_user", "manager_name")
    op.drop_column("partner_user", "manager_id")
    op.drop_column("partner_user", "perm_scope")
    op.drop_column("partner_user", "account_type")
    op.drop_table("crm_partner_staff")
    op.drop_table("task_entrust_item")
    op.drop_table("task_entrust")
