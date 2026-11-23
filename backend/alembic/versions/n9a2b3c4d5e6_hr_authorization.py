"""人事行政：人员授权台账（B9-C3）

- `hr_authorization`：一行 = 某人在某段时间、某范围内、以某个角色获得的授权；
  范围四维（检测方法 / 设备 / 业务域）显式建模可索引，`scope_json` 只做展示快照；
- `hr_authorization_event`：授权变更轨迹，**只追加**（无 deleted / version / update_*），
  用于回溯任一历史时点的授权状态。

手工迁移：`alembic/env.py` 未 import hr 域 models，autogenerate 会试图删表。

Revision ID: n9a2b3c4d5e6
Revises: n8a2b3c4d5e6
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "n9a2b3c4d5e6"
down_revision = "n8a2b3c4d5e6"
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

_APPEND_ONLY_COLS = [
    sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
    sa.Column("create_time", sa.DateTime(), server_default=sa.text("now()"), nullable=False, comment="写入时间"),
]


def upgrade() -> None:
    op.create_table(
        "hr_authorization",
        sa.Column("auth_no", sa.String(32), nullable=False, comment="授权编号 AU..."),
        sa.Column("user_id", sa.BigInteger(), nullable=False, comment="被授权人 sys_user.id"),
        sa.Column("user_name", sa.String(64), nullable=False, server_default="", comment="被授权人姓名"),
        sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="部门 id"),
        sa.Column("dept_name", sa.String(64), nullable=False, server_default="", comment="部门名称"),
        sa.Column(
            "auth_type",
            sa.String(32),
            nullable=False,
            server_default="test_item",
            comment="授权类型 test_item检测项目/device设备操作/report_role报告角色/signer授权签字",
        ),
        sa.Column(
            "role_code",
            sa.String(32),
            nullable=False,
            server_default="",
            comment="角色 preparer编制/reviewer复核/approver批准/signer签字",
        ),
        sa.Column("scope_method", sa.String(64), nullable=False, server_default="", comment="检测方法/标准"),
        sa.Column("scope_params", sa.String(255), nullable=False, server_default="", comment="方法参数（逗号分隔）"),
        sa.Column("scope_device_id", sa.BigInteger(), nullable=True, comment="设备 id"),
        sa.Column("scope_device_name", sa.String(64), nullable=False, server_default="", comment="设备名称"),
        sa.Column("scope_domain", sa.String(64), nullable=False, server_default="", comment="业务域/专业域"),
        sa.Column("scope_json", sa.Text(), nullable=False, comment="范围快照（展示兜底，不做过滤依据）"),
        sa.Column("valid_from", sa.DateTime(), nullable=True, comment="生效时间"),
        sa.Column("valid_to", sa.DateTime(), nullable=True, comment="失效时间"),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="draft",
            comment="draft/approving/confirmed/active/suspended/expired/revoked/rejected",
        ),
        sa.Column("applicant_id", sa.BigInteger(), nullable=True, comment="申请人 id"),
        sa.Column("applicant_name", sa.String(64), nullable=False, server_default="", comment="申请人姓名"),
        sa.Column("approver_id", sa.BigInteger(), nullable=True, comment="批准人 id"),
        sa.Column("approver_name", sa.String(64), nullable=False, server_default="", comment="批准人姓名"),
        sa.Column("approved_at", sa.DateTime(), nullable=True, comment="批准时间"),
        sa.Column("activated_at", sa.DateTime(), nullable=True, comment="生效时间"),
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="审批实例 approval_instance.id"),
        sa.Column("last_reason", sa.String(500), nullable=False, server_default="", comment="最近一次状态变更原因"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_authorization_auth_no", "hr_authorization", ["auth_no"], unique=True)
    op.create_index("ix_hr_authorization_user_id", "hr_authorization", ["user_id"])
    op.create_index("ix_hr_authorization_dept_id", "hr_authorization", ["dept_id"])
    op.create_index("ix_hr_authorization_auth_type", "hr_authorization", ["auth_type"])
    op.create_index("ix_hr_authorization_status", "hr_authorization", ["status"])
    op.create_index("ix_hr_authorization_flow_instance_id", "hr_authorization", ["flow_instance_id"])
    op.create_index(
        "ix_hr_authorization_user_type_status", "hr_authorization", ["user_id", "auth_type", "status"]
    )
    op.create_index("ix_hr_authorization_type_status", "hr_authorization", ["auth_type", "status"])
    op.create_index("ix_hr_authorization_status_valid_to", "hr_authorization", ["status", "valid_to"])

    op.create_table(
        "hr_authorization_event",
        sa.Column("authorization_id", sa.BigInteger(), nullable=False, comment="授权 id"),
        sa.Column("auth_no", sa.String(32), nullable=False, server_default="", comment="授权编号快照"),
        sa.Column(
            "event_type",
            sa.String(32),
            nullable=False,
            server_default="",
            comment="事件类型 create/submit/approve/activate/suspend/resume/revoke/expire",
        ),
        sa.Column("from_status", sa.String(16), nullable=False, server_default="", comment="变更前状态"),
        sa.Column("to_status", sa.String(16), nullable=False, server_default="", comment="变更后状态"),
        sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人 id"),
        sa.Column("operator_name", sa.String(64), nullable=False, server_default="", comment="操作人姓名"),
        sa.Column("reason", sa.String(500), nullable=False, server_default="", comment="变更原因"),
        sa.Column("effective_at", DATETIME(fsp=3), nullable=True, comment="生效时间（毫秒精度）"),
        sa.Column("snapshot", sa.Text(), nullable=False, comment="变更时点的授权快照 JSON"),
        *_APPEND_ONLY_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_authorization_event_authorization_id", "hr_authorization_event", ["authorization_id"])
    op.create_index("ix_hr_authorization_event_effective_at", "hr_authorization_event", ["effective_at"])
    op.create_index(
        "ix_hr_authorization_event_auth_id_at", "hr_authorization_event", ["authorization_id", "effective_at"]
    )
    op.create_index("ix_hr_authorization_event_auth_no", "hr_authorization_event", ["auth_no"])


def downgrade() -> None:
    op.drop_table("hr_authorization_event")
    op.drop_table("hr_authorization")
