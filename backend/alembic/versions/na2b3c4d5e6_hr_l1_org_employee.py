"""HR L1：组织架构 + 员工主数据 + 人事事务（B10-1）

- `sys_dept` 扩展 6 列：`dept_type`（场所/科室层级）、`site_code`（多场所）、
  `address`、`manager_id`（部门负责人）、`effective_from/to`（有效期）。
  `sys_dept` 仍是**全站唯一的部门表**，不新建组织树；
- `hr_position`：岗位说明书 + 关键岗位标记 + A/B 角；
- `hr_employee`：员工一人一档（证件号 AES-GCM 密文）；
- `hr_employee_control`：黑白名单；
- `hr_employment` / `hr_employment_event`：人事事务单据 + **只追加**变更轨迹；
- `hr_delegate`：代理人（AB 角 / 临时代理，不借账号）；
- `hr_org_change`：**只追加**组织变更快照（历史版本留存）。

手工迁移：`alembic/env.py` 未 import hr 域 models，autogenerate 会试图删表。

Revision ID: na2b3c4d5e6
Revises: n9a2b3c4d5e6
Create Date: 2026-11-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import DATETIME

revision = "na2b3c4d5e6"
down_revision = "n9a2b3c4d5e6"
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
    # ------------------------------------------------------------------
    # sys_dept 扩展（组织架构：多场所 / 层级 / 负责人 / 有效期）
    # ------------------------------------------------------------------
    op.add_column("sys_dept", sa.Column("dept_type", sa.String(16), nullable=False, server_default="dept", comment="层级 site场所/company公司/division事业部/dept科室/lab实验室/team班组"))
    op.add_column("sys_dept", sa.Column("site_code", sa.String(32), nullable=False, server_default="", comment="场所编码（多场所）"))
    op.add_column("sys_dept", sa.Column("address", sa.String(255), nullable=False, server_default="", comment="办公地址"))
    op.add_column("sys_dept", sa.Column("manager_id", sa.BigInteger(), nullable=True, comment="部门负责人 sys_user.id"))
    op.add_column("sys_dept", sa.Column("effective_from", sa.Date(), nullable=True, comment="生效日期"))
    op.add_column("sys_dept", sa.Column("effective_to", sa.Date(), nullable=True, comment="失效日期"))
    op.create_index("ix_sys_dept_dept_type", "sys_dept", ["dept_type"])
    op.create_index("ix_sys_dept_site_code", "sys_dept", ["site_code"])
    op.create_index("ix_sys_dept_manager_id", "sys_dept", ["manager_id"])

    # ------------------------------------------------------------------
    # hr_position：岗位
    # ------------------------------------------------------------------
    op.create_table(
        "hr_position",
        sa.Column("code", sa.String(32), nullable=False, comment="岗位编码"),
        sa.Column("name", sa.String(128), nullable=False, comment="岗位名称"),
        sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="所属部门 sys_dept.id"),
        sa.Column("site_id", sa.BigInteger(), nullable=True, comment="所属场所 sys_dept.id"),
        sa.Column("position_type", sa.String(16), nullable=False, server_default="staff", comment="岗位类型 staff/manager/key"),
        sa.Column("duty", sa.Text(), nullable=False, comment="岗位职责"),
        sa.Column("requirement", sa.Text(), nullable=False, comment="任职要求"),
        sa.Column("report_to_id", sa.BigInteger(), nullable=True, comment="汇报岗位 hr_position.id"),
        sa.Column("key_role", sa.String(32), nullable=False, server_default="", comment="关键岗位标记"),
        sa.Column("primary_user_id", sa.BigInteger(), nullable=True, comment="A 角 sys_user.id"),
        sa.Column("backup_user_id", sa.BigInteger(), nullable=True, comment="B 角 sys_user.id"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled", comment="enabled/disabled"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_position_code", "hr_position", ["code"], unique=True)
    op.create_index("ix_hr_position_name", "hr_position", ["name"])
    op.create_index("ix_hr_position_dept_id", "hr_position", ["dept_id"])
    op.create_index("ix_hr_position_site_id", "hr_position", ["site_id"])
    op.create_index("ix_hr_position_position_type", "hr_position", ["position_type"])
    op.create_index("ix_hr_position_report_to_id", "hr_position", ["report_to_id"])
    op.create_index("ix_hr_position_key_role", "hr_position", ["key_role"])
    op.create_index("ix_hr_position_primary_user_id", "hr_position", ["primary_user_id"])
    op.create_index("ix_hr_position_backup_user_id", "hr_position", ["backup_user_id"])
    op.create_index("ix_hr_position_status", "hr_position", ["status"])
    op.create_index("ix_hr_position_dept_status", "hr_position", ["dept_id", "status"])
    op.create_index("ix_hr_position_key_role_status", "hr_position", ["key_role", "status"])
    op.create_index("ix_hr_position_site_status", "hr_position", ["site_id", "status"])

    # ------------------------------------------------------------------
    # hr_employee：员工一人一档
    # ------------------------------------------------------------------
    op.create_table(
        "hr_employee",
        sa.Column("employee_no", sa.String(32), nullable=False, comment="工号"),
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="关联账号 sys_user.id"),
        sa.Column("name", sa.String(64), nullable=False, comment="姓名"),
        sa.Column("id_no", sa.String(255), nullable=False, server_default="", comment="证件号（AES-GCM 密文 enc: 前缀）"),
        sa.Column("id_type", sa.String(16), nullable=False, server_default="id_card", comment="证件类型"),
        sa.Column("gender", sa.String(8), nullable=False, server_default="", comment="性别"),
        sa.Column("birth_date", sa.Date(), nullable=True, comment="出生日期"),
        sa.Column("education", sa.String(32), nullable=False, server_default="", comment="学历"),
        sa.Column("major", sa.String(64), nullable=False, server_default="", comment="专业"),
        sa.Column("mobile", sa.String(32), nullable=False, server_default="", comment="手机号"),
        sa.Column("email", sa.String(128), nullable=False, server_default="", comment="邮箱"),
        sa.Column("employ_type", sa.String(16), nullable=False, server_default="labor", comment="雇佣类型"),
        sa.Column("employ_status", sa.String(16), nullable=False, server_default="probation", comment="在职状态"),
        sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="所属部门 sys_dept.id"),
        sa.Column("position_id", sa.BigInteger(), nullable=True, comment="岗位 hr_position.id"),
        sa.Column("hire_date", sa.Date(), nullable=True, comment="入职日期"),
        sa.Column("leave_date", sa.Date(), nullable=True, comment="离职日期"),
        sa.Column("contract_no", sa.String(64), nullable=False, server_default="", comment="劳动合同编号"),
        sa.Column("contract_start", sa.Date(), nullable=True, comment="合同起始"),
        sa.Column("contract_end", sa.Date(), nullable=True, comment="合同到期"),
        sa.Column("emergency_contact", sa.String(64), nullable=False, server_default="", comment="紧急联系人"),
        sa.Column("emergency_mobile", sa.String(32), nullable=False, server_default="", comment="紧急联系电话"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled", comment="档案状态"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_employee_employee_no", "hr_employee", ["employee_no"], unique=True)
    op.create_index("ix_hr_employee_user_id", "hr_employee", ["user_id"])
    op.create_index("ix_hr_employee_name", "hr_employee", ["name"])
    op.create_index("ix_hr_employee_education", "hr_employee", ["education"])
    op.create_index("ix_hr_employee_mobile", "hr_employee", ["mobile"])
    op.create_index("ix_hr_employee_employ_type", "hr_employee", ["employ_type"])
    op.create_index("ix_hr_employee_employ_status", "hr_employee", ["employ_status"])
    op.create_index("ix_hr_employee_dept_id", "hr_employee", ["dept_id"])
    op.create_index("ix_hr_employee_position_id", "hr_employee", ["position_id"])
    op.create_index("ix_hr_employee_hire_date", "hr_employee", ["hire_date"])
    op.create_index("ix_hr_employee_status", "hr_employee", ["status"])
    op.create_index("ix_hr_employee_status_dept", "hr_employee", ["employ_status", "dept_id"])
    op.create_index("ix_hr_employee_user", "hr_employee", ["user_id"])

    # ------------------------------------------------------------------
    # hr_employee_control：黑白名单
    # ------------------------------------------------------------------
    op.create_table(
        "hr_employee_control",
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="员工 hr_employee.id"),
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="关联账号 sys_user.id"),
        sa.Column("control_type", sa.String(16), nullable=False, comment="名单类型 blacklist/whitelist"),
        sa.Column("reason", sa.String(500), nullable=False, server_default="", comment="原因"),
        sa.Column("effective_from", sa.Date(), nullable=True, comment="生效日期"),
        sa.Column("effective_to", sa.Date(), nullable=True, comment="失效日期"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled", comment="enabled/disabled"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("employee_id", "control_type", "deleted", name="uq_hr_emp_control_type"),
    )
    op.create_index("ix_hr_employee_control_employee_id", "hr_employee_control", ["employee_id"])
    op.create_index("ix_hr_employee_control_user_id", "hr_employee_control", ["user_id"])
    op.create_index("ix_hr_employee_control_control_type", "hr_employee_control", ["control_type"])
    op.create_index("ix_hr_employee_control_status", "hr_employee_control", ["status"])

    # ------------------------------------------------------------------
    # hr_employment：人事事务单据
    # ------------------------------------------------------------------
    op.create_table(
        "hr_employment",
        sa.Column("emp_no", sa.String(32), nullable=False, comment="人事事务单号 EM..."),
        sa.Column("event_type", sa.String(16), nullable=False, comment="事务类型 onboard/transfer/resign/rehire"),
        sa.Column("employee_id", sa.BigInteger(), nullable=False, comment="员工 hr_employee.id"),
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="关联账号 sys_user.id"),
        sa.Column("user_name", sa.String(64), nullable=False, server_default="", comment="员工姓名快照"),
        sa.Column("dept_id", sa.BigInteger(), nullable=True, comment="原部门"),
        sa.Column("dept_name", sa.String(64), nullable=False, server_default="", comment="原部门名称"),
        sa.Column("new_dept_id", sa.BigInteger(), nullable=True, comment="新部门"),
        sa.Column("new_dept_name", sa.String(64), nullable=False, server_default="", comment="新部门名称"),
        sa.Column("position_id", sa.BigInteger(), nullable=True, comment="原岗位"),
        sa.Column("position_name", sa.String(64), nullable=False, server_default="", comment="原岗位名称"),
        sa.Column("new_position_id", sa.BigInteger(), nullable=True, comment="新岗位"),
        sa.Column("new_position_name", sa.String(64), nullable=False, server_default="", comment="新岗位名称"),
        sa.Column("effective_date", sa.Date(), nullable=True, comment="生效日期"),
        sa.Column("reason", sa.String(500), nullable=False, server_default="", comment="事由"),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft", comment="draft/approving/approved/effective/rejected"),
        sa.Column("flow_instance_id", sa.BigInteger(), nullable=True, comment="审批实例 approval_instance.id"),
        sa.Column("applicant_id", sa.BigInteger(), nullable=True, comment="申请人 id"),
        sa.Column("applicant_name", sa.String(64), nullable=False, server_default="", comment="申请人姓名"),
        sa.Column("approver_id", sa.BigInteger(), nullable=True, comment="批准人 id"),
        sa.Column("approver_name", sa.String(64), nullable=False, server_default="", comment="批准人姓名"),
        sa.Column("approved_at", sa.DateTime(), nullable=True, comment="批准时间"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_employment_emp_no", "hr_employment", ["emp_no"], unique=True)
    op.create_index("ix_hr_employment_event_type", "hr_employment", ["event_type"])
    op.create_index("ix_hr_employment_employee_id", "hr_employment", ["employee_id"])
    op.create_index("ix_hr_employment_user_id", "hr_employment", ["user_id"])
    op.create_index("ix_hr_employment_dept_id", "hr_employment", ["dept_id"])
    op.create_index("ix_hr_employment_new_dept_id", "hr_employment", ["new_dept_id"])
    op.create_index("ix_hr_employment_position_id", "hr_employment", ["position_id"])
    op.create_index("ix_hr_employment_new_position_id", "hr_employment", ["new_position_id"])
    op.create_index("ix_hr_employment_effective_date", "hr_employment", ["effective_date"])
    op.create_index("ix_hr_employment_status", "hr_employment", ["status"])
    op.create_index("ix_hr_employment_flow_instance_id", "hr_employment", ["flow_instance_id"])
    op.create_index("ix_hr_employment_applicant_id", "hr_employment", ["applicant_id"])
    op.create_index("ix_hr_employment_event_status", "hr_employment", ["event_type", "status"])
    op.create_index("ix_hr_employment_employee", "hr_employment", ["employee_id"])

    # ------------------------------------------------------------------
    # hr_employment_event：人事事务变更轨迹（只追加）
    # ------------------------------------------------------------------
    op.create_table(
        "hr_employment_event",
        sa.Column("employment_id", sa.BigInteger(), nullable=False, comment="人事事务 id"),
        sa.Column("emp_no", sa.String(32), nullable=False, server_default="", comment="单号快照"),
        sa.Column("event_type", sa.String(32), nullable=False, server_default="", comment="事件类型"),
        sa.Column("from_status", sa.String(16), nullable=False, server_default="", comment="变更前状态"),
        sa.Column("to_status", sa.String(16), nullable=False, server_default="", comment="变更后状态"),
        sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人 id"),
        sa.Column("operator_name", sa.String(64), nullable=False, server_default="", comment="操作人姓名"),
        sa.Column("reason", sa.String(500), nullable=False, server_default="", comment="变更原因"),
        sa.Column("effective_at", DATETIME(fsp=3), nullable=True, comment="生效时间（毫秒精度）"),
        sa.Column("snapshot", sa.Text(), nullable=False, comment="变更时点的人事事务快照 JSON"),
        *_APPEND_ONLY_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_employment_event_employment_id", "hr_employment_event", ["employment_id"])
    op.create_index("ix_hr_employment_event_effective_at", "hr_employment_event", ["effective_at"])
    op.create_index("ix_hr_emp_event_emp_id_at", "hr_employment_event", ["employment_id", "effective_at"])
    op.create_index("ix_hr_emp_event_emp_no", "hr_employment_event", ["emp_no"])

    # ------------------------------------------------------------------
    # hr_delegate：代理人
    # ------------------------------------------------------------------
    op.create_table(
        "hr_delegate",
        sa.Column("principal_id", sa.BigInteger(), nullable=False, comment="委托人 sys_user.id"),
        sa.Column("principal_name", sa.String(64), nullable=False, server_default="", comment="委托人姓名"),
        sa.Column("agent_id", sa.BigInteger(), nullable=False, comment="代理人 sys_user.id"),
        sa.Column("agent_name", sa.String(64), nullable=False, server_default="", comment="代理人姓名"),
        sa.Column("scope", sa.String(32), nullable=False, server_default="position", comment="代理范围 position/auth/task"),
        sa.Column("position_id", sa.BigInteger(), nullable=True, comment="关联岗位 hr_position.id"),
        sa.Column("auth_id", sa.BigInteger(), nullable=True, comment="关联授权 hr_authorization.id"),
        sa.Column("reason", sa.String(500), nullable=False, server_default="", comment="事由"),
        sa.Column("effective_from", sa.DateTime(), nullable=True, comment="生效时间"),
        sa.Column("effective_to", sa.DateTime(), nullable=True, comment="失效时间"),
        sa.Column("status", sa.String(16), nullable=False, server_default="enabled", comment="enabled/expired/revoked"),
        sa.Column("auto_takeover", sa.Integer(), nullable=False, server_default="0", comment="委托人离岗自动接管标记"),
        sa.Column("remark", sa.String(500), nullable=False, server_default="", comment="备注"),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_delegate_principal_id", "hr_delegate", ["principal_id"])
    op.create_index("ix_hr_delegate_agent_id", "hr_delegate", ["agent_id"])
    op.create_index("ix_hr_delegate_scope", "hr_delegate", ["scope"])
    op.create_index("ix_hr_delegate_position_id", "hr_delegate", ["position_id"])
    op.create_index("ix_hr_delegate_auth_id", "hr_delegate", ["auth_id"])
    op.create_index("ix_hr_delegate_effective_from", "hr_delegate", ["effective_from"])
    op.create_index("ix_hr_delegate_effective_to", "hr_delegate", ["effective_to"])
    op.create_index("ix_hr_delegate_status", "hr_delegate", ["status"])
    op.create_index("ix_hr_delegate_principal", "hr_delegate", ["principal_id", "status"])
    op.create_index("ix_hr_delegate_agent", "hr_delegate", ["agent_id", "status"])

    # ------------------------------------------------------------------
    # hr_org_change：组织变更轨迹（只追加）
    # ------------------------------------------------------------------
    op.create_table(
        "hr_org_change",
        sa.Column("object_type", sa.String(16), nullable=False, comment="对象类型 dept/position/employee"),
        sa.Column("object_id", sa.BigInteger(), nullable=False, comment="对象 id"),
        sa.Column("object_name", sa.String(128), nullable=False, server_default="", comment="对象名称快照"),
        sa.Column("change_type", sa.String(32), nullable=False, server_default="", comment="变更类型"),
        sa.Column("before_json", sa.Text(), nullable=False, comment="变更前快照 JSON"),
        sa.Column("after_json", sa.Text(), nullable=False, comment="变更后快照 JSON"),
        sa.Column("operator_id", sa.BigInteger(), nullable=True, comment="操作人 id"),
        sa.Column("operator_name", sa.String(64), nullable=False, server_default="", comment="操作人姓名"),
        sa.Column("effective_at", DATETIME(fsp=3), nullable=True, comment="生效时间（毫秒精度）"),
        sa.Column("reason", sa.String(500), nullable=False, server_default="", comment="变更原因"),
        *_APPEND_ONLY_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_hr_org_change_object_type", "hr_org_change", ["object_type"])
    op.create_index("ix_hr_org_change_object_id", "hr_org_change", ["object_id"])
    op.create_index("ix_hr_org_change_effective_at", "hr_org_change", ["effective_at"])
    op.create_index("ix_hr_org_change_obj", "hr_org_change", ["object_type", "object_id", "effective_at"])


def downgrade() -> None:
    op.drop_table("hr_org_change")
    op.drop_table("hr_delegate")
    op.drop_table("hr_employment_event")
    op.drop_table("hr_employment")
    op.drop_table("hr_employee_control")
    op.drop_table("hr_employee")
    op.drop_table("hr_position")

    op.drop_index("ix_sys_dept_manager_id", table_name="sys_dept")
    op.drop_index("ix_sys_dept_site_code", table_name="sys_dept")
    op.drop_index("ix_sys_dept_dept_type", table_name="sys_dept")
    op.drop_column("sys_dept", "effective_to")
    op.drop_column("sys_dept", "effective_from")
    op.drop_column("sys_dept", "manager_id")
    op.drop_column("sys_dept", "address")
    op.drop_column("sys_dept", "site_code")
    op.drop_column("sys_dept", "dept_type")
