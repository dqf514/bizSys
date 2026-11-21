"""B3 访客与安全：区域分级 / 访客登记审批 / 通行凭证 / 合规审计（只追加）/ NDA / 黑名单 / 样品交接 / 预警

Revision ID: n3a2b3c4d5e6
Revises: n2a2b3c4d5e6
Create Date: 2026-11-21
"""
import sqlalchemy as sa
from alembic import op

revision = "n3a2b3c4d5e6"
down_revision = "n2a2b3c4d5e6"
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


def _create(table: str, cols: list, indexes: list | None = None) -> None:
    op.create_table(
        table,
        *_base_cols(),
        *cols,
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    for idx in indexes or []:
        op.create_index(idx["name"], table, idx["cols"], unique=idx.get("unique", False))


def upgrade() -> None:
    # ---------------- 区域与分级 ----------------
    _create(
        "vis_zone",
        [
            sa.Column("code", sa.String(32), nullable=True, comment="区域编码"),
            sa.Column("name", sa.String(64), nullable=True, comment="区域名称"),
            sa.Column("zone_type", sa.String(32), nullable=True, comment="区域类型"),
            sa.Column("security_level", sa.Integer(), nullable=True, comment="安全等级 1-4"),
            sa.Column("need_extra_approval", sa.Integer(), nullable=True, comment="敏感区域需额外审批"),
            sa.Column("need_escort", sa.Integer(), nullable=True, comment="需陪同"),
            sa.Column("need_nda", sa.Integer(), nullable=True, comment="需签保密协议"),
            sa.Column("need_dual_person", sa.Integer(), nullable=True, comment="高危作业需双人"),
            sa.Column("camera_control", sa.Integer(), nullable=True, comment="手机相机管控"),
            sa.Column("device_binding", sa.String(255), nullable=True, comment="联动设备"),
            sa.Column("capacity", sa.Integer(), nullable=True, comment="同时在场人数上限，0 不限"),
            sa.Column("status", sa.String(16), nullable=True, comment="enabled/disabled"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_vis_zone_code", "cols": ["code"]},
            {"name": "ix_vis_zone_zone_type", "cols": ["zone_type"]},
            {"name": "ix_vis_zone_status", "cols": ["status"]},
        ],
    )

    # ---------------- 访客登记单 ----------------
    _create(
        "vis_visit",
        [
            sa.Column("visit_no", sa.String(32), nullable=True, comment="访客单号 VT..."),
            sa.Column("visitor_name", sa.String(64), nullable=True, comment="访客姓名"),
            sa.Column("visitor_company", sa.String(128), nullable=True, comment="访客单位"),
            sa.Column("visitor_type", sa.String(32), nullable=True, comment="访客类型"),
            sa.Column("id_no", sa.String(64), nullable=True, comment="证件号"),
            sa.Column("phone", sa.String(32), nullable=True, comment="联系电话"),
            sa.Column("plate_no", sa.String(32), nullable=True, comment="车牌号"),
            sa.Column("host_user_id", sa.BigInteger(), nullable=True, comment="被访人 id"),
            sa.Column("host_name", sa.String(64), nullable=True, comment="被访人姓名"),
            sa.Column("host_dept_id", sa.BigInteger(), nullable=True, comment="被访部门 id"),
            sa.Column("host_dept_name", sa.String(128), nullable=True, comment="被访部门"),
            sa.Column("purpose", sa.String(255), nullable=True, comment="来访事由"),
            sa.Column("source", sa.String(16), nullable=True, comment="来源"),
            sa.Column("zone_ids", sa.Text(), nullable=True, comment="可进入区域 id 列表"),
            sa.Column("escort_names", sa.Text(), nullable=True, comment="陪同与见证人"),
            sa.Column("plan_start", sa.DateTime(), nullable=True, comment="计划进入"),
            sa.Column("plan_end", sa.DateTime(), nullable=True, comment="计划离开"),
            sa.Column("checkin_at", sa.DateTime(), nullable=True, comment="实际签入"),
            sa.Column("checkout_at", sa.DateTime(), nullable=True, comment="实际签出"),
            sa.Column("status", sa.String(16), nullable=True, comment="pending/approved/rejected/visiting/left/overdue/cancelled"),
            sa.Column("required_levels", sa.String(64), nullable=True, comment="需要的审批层级"),
            sa.Column("approved_levels", sa.String(64), nullable=True, comment="已通过的审批层级"),
            sa.Column("nda_id", sa.BigInteger(), nullable=True, comment="关联 NDA"),
            sa.Column("credential_id", sa.BigInteger(), nullable=True, comment="关联通行凭证"),
            sa.Column("credential_no", sa.String(32), nullable=True, comment="凭证编号"),
            sa.Column("staff_id", sa.BigInteger(), nullable=True, comment="客户方人员备案 id"),
            sa.Column("customer_id", sa.BigInteger(), nullable=True, comment="关联往来单位 id"),
            sa.Column("customer_name", sa.String(128), nullable=True, comment="关联往来单位"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_vis_visit_visit_no", "cols": ["visit_no"]},
            {"name": "ix_vis_visit_visitor_name", "cols": ["visitor_name"]},
            {"name": "ix_vis_visit_status", "cols": ["status"]},
            {"name": "ix_vis_visit_plan_start", "cols": ["plan_start"]},
        ],
    )

    # ---------------- 审批记录 ----------------
    _create(
        "vis_approval",
        [
            sa.Column("visit_id", sa.BigInteger(), nullable=True, comment="访客单 id"),
            sa.Column("level", sa.String(32), nullable=True, comment="审批层级 host/dept/zone"),
            sa.Column("approver_id", sa.BigInteger(), nullable=True, comment="审批人 id"),
            sa.Column("approver_name", sa.String(64), nullable=True, comment="审批人姓名"),
            sa.Column("action", sa.String(16), nullable=True, comment="approve/reject"),
            sa.Column("comment", sa.Text(), nullable=True, comment="审批意见"),
            sa.Column("decided_at", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="审批时间"),
        ],
        [
            {"name": "ix_vis_approval_visit_id", "cols": ["visit_id"]},
        ],
    )

    # ---------------- 通行凭证 ----------------
    _create(
        "vis_credential",
        [
            sa.Column("credential_no", sa.String(32), nullable=True, comment="凭证编号 VC..."),
            sa.Column("visit_id", sa.BigInteger(), nullable=True, comment="访客单 id"),
            sa.Column("visitor_name", sa.String(64), nullable=True, comment="访客姓名"),
            sa.Column("credential_type", sa.String(16), nullable=True, comment="qrcode/face/ic/plate"),
            sa.Column("zone_ids", sa.Text(), nullable=True, comment="授权区域 id 列表"),
            sa.Column("valid_from", sa.DateTime(), nullable=True, comment="生效时间"),
            sa.Column("valid_to", sa.DateTime(), nullable=True, comment="失效时间"),
            sa.Column("status", sa.String(16), nullable=True, comment="issued/used/expired/revoked"),
            sa.Column("code", sa.String(255), nullable=True, comment="凭证载荷"),
            sa.Column("used_at", sa.DateTime(), nullable=True, comment="最近核验时间"),
            sa.Column("used_count", sa.Integer(), nullable=True, comment="核验次数"),
        ],
        [
            {"name": "ix_vis_credential_credential_no", "cols": ["credential_no"]},
            {"name": "ix_vis_credential_visit_id", "cols": ["visit_id"]},
            {"name": "ix_vis_credential_status", "cols": ["status"]},
        ],
    )

    # ---------------- 合规审计日志（只追加，无 deleted / version） ----------------
    op.create_table(
        "vis_access_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="写入时间"),
        sa.Column("visit_id", sa.BigInteger(), nullable=True, comment="访客单 id"),
        sa.Column("credential_id", sa.BigInteger(), nullable=True, comment="凭证 id"),
        sa.Column("credential_no", sa.String(32), nullable=True, comment="凭证编号"),
        sa.Column("visitor_name", sa.String(64), nullable=True, comment="访客姓名"),
        sa.Column("zone_id", sa.BigInteger(), nullable=True, comment="区域 id"),
        sa.Column("zone_name", sa.String(64), nullable=True, comment="区域名称"),
        sa.Column("direction", sa.String(8), nullable=True, comment="in/out"),
        sa.Column("event_type", sa.String(32), nullable=True, comment="事件类型"),
        sa.Column("method", sa.String(16), nullable=True, comment="核验方式"),
        sa.Column("result", sa.String(8), nullable=True, comment="pass/deny"),
        sa.Column("device_id", sa.String(64), nullable=True, comment="门禁 / 闸机 / 梯控设备号"),
        sa.Column("operator_name", sa.String(64), nullable=True, comment="操作人"),
        sa.Column("happened_at", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="事件时间"),
        sa.Column("detail", sa.Text(), nullable=True, comment="明细"),
        sa.PrimaryKeyConstraint("id"),
        mysql_charset="utf8mb4",
        mysql_engine="InnoDB",
    )
    op.create_index("ix_vis_access_log_visit_id", "vis_access_log", ["visit_id"])
    op.create_index("ix_vis_access_log_happened_at", "vis_access_log", ["happened_at"])
    op.create_index("ix_vis_access_log_event_type", "vis_access_log", ["event_type"])
    op.create_index("ix_vis_access_log_result", "vis_access_log", ["result"])

    # ---------------- NDA 电子签 ----------------
    _create(
        "vis_nda",
        [
            sa.Column("nda_no", sa.String(32), nullable=True, comment="NDA 编号 ND..."),
            sa.Column("title", sa.String(128), nullable=True, comment="协议标题"),
            sa.Column("template", sa.String(32), nullable=True, comment="模板版本"),
            sa.Column("visitor_name", sa.String(64), nullable=True, comment="签署人姓名"),
            sa.Column("visitor_company", sa.String(128), nullable=True, comment="签署人单位"),
            sa.Column("signer_title", sa.String(64), nullable=True, comment="职务"),
            sa.Column("id_no", sa.String(64), nullable=True, comment="证件号"),
            sa.Column("signed_at", sa.DateTime(), nullable=True, comment="签署时间"),
            sa.Column("signature_data", sa.Text(), nullable=True, comment="签名数据"),
            sa.Column("evidence_hash", sa.String(64), nullable=True, comment="存证哈希"),
            sa.Column("ip", sa.String(64), nullable=True, comment="签署 IP"),
            sa.Column("valid_from", sa.DateTime(), nullable=True, comment="生效时间"),
            sa.Column("valid_to", sa.DateTime(), nullable=True, comment="失效时间"),
            sa.Column("status", sa.String(16), nullable=True, comment="signed/expired/revoked"),
            sa.Column("visit_id", sa.BigInteger(), nullable=True, comment="关联访客单"),
            sa.Column("staff_id", sa.BigInteger(), nullable=True, comment="客户方人员备案 id"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_vis_nda_nda_no", "cols": ["nda_no"]},
            {"name": "ix_vis_nda_visit_id", "cols": ["visit_id"]},
            {"name": "ix_vis_nda_status", "cols": ["status"]},
        ],
    )

    # ---------------- 黑名单 ----------------
    _create(
        "vis_blacklist",
        [
            sa.Column("visitor_name", sa.String(64), nullable=True, comment="姓名"),
            sa.Column("id_no", sa.String(64), nullable=True, comment="证件号"),
            sa.Column("phone", sa.String(32), nullable=True, comment="联系电话"),
            sa.Column("company", sa.String(128), nullable=True, comment="单位"),
            sa.Column("reason", sa.String(255), nullable=True, comment="列入原因"),
            sa.Column("effective_from", sa.DateTime(), nullable=True, comment="生效时间"),
            sa.Column("effective_to", sa.DateTime(), nullable=True, comment="失效时间"),
            sa.Column("source", sa.String(32), nullable=True, comment="来源"),
            sa.Column("status", sa.String(16), nullable=True, comment="enabled/disabled"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_vis_blacklist_visitor_name", "cols": ["visitor_name"]},
            {"name": "ix_vis_blacklist_id_no", "cols": ["id_no"]},
            {"name": "ix_vis_blacklist_status", "cols": ["status"]},
        ],
    )

    # ---------------- 样品 / 样车交接 ----------------
    _create(
        "vis_sample_handover",
        [
            sa.Column("handover_no", sa.String(32), nullable=True, comment="交接单号 SH..."),
            sa.Column("visit_id", sa.BigInteger(), nullable=True, comment="访客单 id"),
            sa.Column("sample_no", sa.String(64), nullable=True, comment="样品 / 样车编号"),
            sa.Column("sample_name", sa.String(128), nullable=True, comment="样品名称"),
            sa.Column("barcode", sa.String(64), nullable=True, comment="条码"),
            sa.Column("sample_type", sa.String(16), nullable=True, comment="sample/vehicle/model"),
            sa.Column("qty", sa.Integer(), nullable=True, comment="数量"),
            sa.Column("handover_user_id", sa.BigInteger(), nullable=True, comment="送样人 id"),
            sa.Column("handover_user_name", sa.String(64), nullable=True, comment="送样人"),
            sa.Column("receive_user_id", sa.BigInteger(), nullable=True, comment="接收人 id"),
            sa.Column("receive_user_name", sa.String(64), nullable=True, comment="接收人"),
            sa.Column("handover_at", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="交接时间"),
            sa.Column("status", sa.String(16), nullable=True, comment="done/returned"),
            sa.Column("remark", sa.Text(), nullable=True, comment="备注"),
        ],
        [
            {"name": "ix_vis_sample_handover_handover_no", "cols": ["handover_no"]},
            {"name": "ix_vis_sample_handover_visit_id", "cols": ["visit_id"]},
            {"name": "ix_vis_sample_handover_sample_no", "cols": ["sample_no"]},
        ],
    )

    # ---------------- 预警 ----------------
    _create(
        "vis_alert",
        [
            sa.Column("visit_id", sa.BigInteger(), nullable=True, comment="访客单 id"),
            sa.Column("alert_type", sa.String(32), nullable=True, comment="预警类型"),
            sa.Column("level", sa.String(16), nullable=True, comment="low/medium/high"),
            sa.Column("zone_id", sa.BigInteger(), nullable=True, comment="区域 id"),
            sa.Column("zone_name", sa.String(64), nullable=True, comment="区域名称"),
            sa.Column("message", sa.String(255), nullable=True, comment="预警描述"),
            sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="发生时间"),
            sa.Column("status", sa.String(16), nullable=True, comment="open/handled/ignored"),
            sa.Column("handled_by", sa.BigInteger(), nullable=True, comment="处理人 id"),
            sa.Column("handled_by_name", sa.String(64), nullable=True, comment="处理人"),
            sa.Column("handled_at", sa.DateTime(), nullable=True, comment="处理时间"),
            sa.Column("handle_remark", sa.Text(), nullable=True, comment="处理说明"),
        ],
        [
            {"name": "ix_vis_alert_visit_id", "cols": ["visit_id"]},
            {"name": "ix_vis_alert_status", "cols": ["status"]},
            {"name": "ix_vis_alert_alert_type", "cols": ["alert_type"]},
        ],
    )


def downgrade() -> None:
    op.drop_table("vis_alert")
    op.drop_table("vis_sample_handover")
    op.drop_table("vis_blacklist")
    op.drop_table("vis_nda")
    op.drop_table("vis_access_log")
    op.drop_table("vis_credential")
    op.drop_table("vis_approval")
    op.drop_table("vis_visit")
    op.drop_table("vis_zone")
