"""B5：任务字段扩展 + 工序/分配/追溯 + 生产排程 + 项目与甘特

- task_task 新增列：plan_start_date / duration_hours / progress / priority / role_group /
  process_stage / mesh_count / solver / compute_resource / compute_cores / compute_nodes
- 新表：task_process（工序流转）、task_assignment（七维分配）、task_trace（全过程追溯）
- 新表：prd_plan（排程方案）、prd_schedule（排程行）
- 新表：prj_project（项目）、prj_project_task（项目任务/甘特行）

production / project 域不在 alembic/env.py 的 metadata 里（与 oa/hr/procurement/sales 同理），
因此本迁移手写。

Revision ID: n5a2b3c4d5e6
Revises: n4a2b3c4d5e6
Create Date: 2026-11-22
"""
import sqlalchemy as sa
from alembic import op

revision = "n5a2b3c4d5e6"
down_revision = "n4a2b3c4d5e6"
branch_labels = None
depends_on = None


def _create(table: str, cols: list, indexes: list | None = None, fks: list | None = None) -> None:
    op.create_table(
        table,
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False, comment="主键"),
        sa.Column("create_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="创建时间"),
        sa.Column("create_by", sa.BigInteger(), nullable=True, comment="创建人"),
        sa.Column("update_time", sa.DateTime(), server_default=sa.func.now(), nullable=True, comment="更新时间"),
        sa.Column("update_by", sa.BigInteger(), nullable=True, comment="更新人"),
        sa.Column("version", sa.Integer(), nullable=True, comment="乐观锁版本"),
        sa.Column("deleted", sa.Integer(), nullable=True, comment="逻辑删除 0/1"),
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
    # ---------------- task_task 扩展列 ----------------
    op.add_column("task_task", sa.Column("plan_start_date", sa.Date(), nullable=True, comment="计划开始日期"))
    op.add_column(
        "task_task", sa.Column("duration_hours", sa.Numeric(10, 2), nullable=True, comment="预计工时（小时），排程用")
    )
    op.add_column("task_task", sa.Column("progress", sa.Integer(), nullable=True, comment="进度百分比 0-100"))
    op.add_column("task_task", sa.Column("priority", sa.Integer(), nullable=True, comment="优先级 1(最高)~9(最低)"))
    op.add_column(
        "task_task",
        sa.Column("role_group", sa.String(32), nullable=True, comment="角色分组：sim/model/test/outsource"),
    )
    op.add_column("task_task", sa.Column("process_stage", sa.String(32), nullable=True, comment="当前工序编码"))
    op.add_column("task_task", sa.Column("mesh_count", sa.Integer(), nullable=True, comment="网格数（万单元）"))
    op.add_column("task_task", sa.Column("solver", sa.String(32), nullable=True, comment="求解器"))
    op.add_column("task_task", sa.Column("compute_resource", sa.String(64), nullable=True, comment="算力资源池"))
    op.add_column("task_task", sa.Column("compute_cores", sa.Integer(), nullable=True, comment="核数"))
    op.add_column("task_task", sa.Column("compute_nodes", sa.Integer(), nullable=True, comment="节点数"))
    op.create_index("ix_task_task_role_group", "task_task", ["role_group"])

    # ---------------- 工序流转 ----------------
    _create(
        "task_process",
        [
            sa.Column("task_id", sa.BigInteger(), nullable=False, comment="所属任务 task_task.id"),
            sa.Column("seq", sa.Integer(), nullable=True, comment="工序序号"),
            sa.Column("process_code", sa.String(32), nullable=True, comment="字典 task_process"),
            sa.Column("process_name", sa.String(64), nullable=True, comment="工序名称冗余"),
            sa.Column("status", sa.String(16), nullable=True, comment="pending/running/done/skipped"),
            sa.Column("is_current", sa.Integer(), nullable=True, comment="是否当前工序"),
            sa.Column("planned_start", sa.Date(), nullable=True),
            sa.Column("planned_end", sa.Date(), nullable=True),
            sa.Column("actual_start", sa.DateTime(), nullable=True),
            sa.Column("actual_end", sa.DateTime(), nullable=True),
            sa.Column("operator_id", sa.BigInteger(), nullable=True),
            sa.Column("operator_name", sa.String(64), nullable=True),
            sa.Column("dept_id", sa.BigInteger(), nullable=True),
            sa.Column("dept_name", sa.String(64), nullable=True),
            sa.Column("remark", sa.String(500), nullable=True),
        ],
        [
            {"name": "ix_task_process_task_id", "cols": ["task_id"]},
            {"name": "ix_task_process_process_code", "cols": ["process_code"]},
            {"name": "ix_task_process_status", "cols": ["status"]},
        ],
        [{"name": "fk_task_process_task", "column": "task_id", "target": "task_task.id", "ondelete": "CASCADE"}],
    )

    # ---------------- 七维分配 ----------------
    _create(
        "task_assignment",
        [
            sa.Column("task_id", sa.BigInteger(), nullable=False, comment="所属任务 task_task.id"),
            sa.Column("dimension", sa.String(16), nullable=True, comment="person/equipment/material/method/env/test/safety/vehicle"),
            sa.Column("resource_id", sa.BigInteger(), nullable=True),
            sa.Column("resource_code", sa.String(64), nullable=True),
            sa.Column("resource_name", sa.String(128), nullable=True),
            sa.Column("qty", sa.Numeric(12, 2), nullable=True, comment="需求量"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("status", sa.String(16), nullable=True, comment="pending/allocated/confirmed/rejected"),
            sa.Column("assigner_id", sa.BigInteger(), nullable=True),
            sa.Column("assigner_name", sa.String(64), nullable=True),
            sa.Column("planned_at", sa.DateTime(), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(), nullable=True),
            sa.Column("remark", sa.String(500), nullable=True),
        ],
        [
            {"name": "ix_task_assignment_task_id", "cols": ["task_id"]},
            {"name": "ix_task_assignment_dimension", "cols": ["dimension"]},
            {"name": "ix_task_assignment_resource_id", "cols": ["resource_id"]},
            {"name": "ix_task_assignment_status", "cols": ["status"]},
        ],
        [{"name": "fk_task_assignment_task", "column": "task_id", "target": "task_task.id", "ondelete": "CASCADE"}],
    )

    # ---------------- 全过程追溯 ----------------
    _create(
        "task_trace",
        [
            sa.Column("task_id", sa.BigInteger(), nullable=False, comment="所属任务 task_task.id"),
            sa.Column("node_code", sa.String(32), nullable=True, comment="input/output_report/vehicle_return/model_ship/accept/settle"),
            sa.Column("node_name", sa.String(64), nullable=True),
            sa.Column("seq", sa.Integer(), nullable=True),
            sa.Column("happen_at", sa.DateTime(), nullable=True),
            sa.Column("ref_no", sa.String(64), nullable=True, comment="关联单号（报告号 / 样车 VIN）"),
            sa.Column("operator_id", sa.BigInteger(), nullable=True),
            sa.Column("operator_name", sa.String(64), nullable=True),
            sa.Column("remark", sa.String(500), nullable=True),
        ],
        [
            {"name": "ix_task_trace_task_id", "cols": ["task_id"]},
            {"name": "ix_task_trace_node_code", "cols": ["node_code"]},
        ],
        [{"name": "fk_task_trace_task", "column": "task_id", "target": "task_task.id", "ondelete": "CASCADE"}],
    )

    # ---------------- 排程方案 ----------------
    _create(
        "prd_plan",
        [
            sa.Column("plan_no", sa.String(32), nullable=False, comment="方案号 PL..."),
            sa.Column("name", sa.String(128), nullable=True, comment="方案名称"),
            sa.Column("plan_date", sa.Date(), nullable=True, comment="排期基准日"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/published/confirmed/cancelled"),
            sa.Column("auto_generated", sa.Integer(), nullable=True, comment="是否自动生成"),
            sa.Column("task_count", sa.Integer(), nullable=True, comment="排程任务数"),
            sa.Column("conflict_count", sa.Integer(), nullable=True, comment="冲突行数"),
            sa.Column("generated_by", sa.BigInteger(), nullable=True),
            sa.Column("generated_by_name", sa.String(64), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("published_by_name", sa.String(64), nullable=True),
            sa.Column("remark", sa.String(500), nullable=True),
        ],
        [
            {"name": "ix_prd_plan_plan_no", "cols": ["plan_no"], "unique": True},
            {"name": "ix_prd_plan_status", "cols": ["status"]},
        ],
    )

    # ---------------- 排程行 ----------------
    _create(
        "prd_schedule",
        [
            sa.Column("schedule_no", sa.String(32), nullable=False, comment="排程编号 SC..."),
            sa.Column("plan_id", sa.BigInteger(), nullable=True, comment="所属方案 prd_plan.id"),
            sa.Column("plan_no_text", sa.String(32), nullable=True, comment="方案号冗余"),
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment="任务 task_task.id"),
            sa.Column("task_no", sa.String(32), nullable=True),
            sa.Column("task_name", sa.String(128), nullable=True),
            sa.Column("project_id", sa.BigInteger(), nullable=True, comment="项目 prj_project.id"),
            sa.Column("project_no", sa.String(32), nullable=True),
            sa.Column("resource_type", sa.String(16), nullable=True, comment="equipment/person/vehicle/material"),
            sa.Column("resource_id", sa.BigInteger(), nullable=True),
            sa.Column("resource_code", sa.String(64), nullable=True),
            sa.Column("resource_name", sa.String(128), nullable=True),
            sa.Column("quantity", sa.Numeric(12, 2), nullable=True, comment="占用数量"),
            sa.Column("unit", sa.String(16), nullable=True),
            sa.Column("plan_start", sa.DateTime(), nullable=True, comment="计划开始"),
            sa.Column("plan_end", sa.DateTime(), nullable=True, comment="计划结束"),
            sa.Column("duration_hours", sa.Numeric(10, 2), nullable=True, comment="时长（小时）"),
            sa.Column("priority", sa.Integer(), nullable=True),
            sa.Column("seq", sa.Integer(), nullable=True, comment="方案内顺序"),
            sa.Column("status", sa.String(16), nullable=True, comment="scheduled/published/confirmed/done/conflict/cancelled"),
            sa.Column("source", sa.String(8), nullable=True, comment="auto / manual"),
            sa.Column("conflict_reason", sa.String(255), nullable=True, comment="冲突原因"),
            sa.Column("remark", sa.String(500), nullable=True),
        ],
        [
            {"name": "ix_prd_schedule_schedule_no", "cols": ["schedule_no"], "unique": True},
            {"name": "ix_prd_schedule_plan_id", "cols": ["plan_id"]},
            {"name": "ix_prd_schedule_task_id", "cols": ["task_id"]},
            {"name": "ix_prd_schedule_task_no", "cols": ["task_no"]},
            {"name": "ix_prd_schedule_project_id", "cols": ["project_id"]},
            {"name": "ix_prd_schedule_resource_type", "cols": ["resource_type"]},
            {"name": "ix_prd_schedule_plan_start", "cols": ["plan_start"]},
            {"name": "ix_prd_schedule_plan_end", "cols": ["plan_end"]},
            {"name": "ix_prd_schedule_status", "cols": ["status"]},
        ],
        [{"name": "fk_prd_schedule_plan", "column": "plan_id", "target": "prd_plan.id", "ondelete": "CASCADE"}],
    )

    # ---------------- 项目 ----------------
    _create(
        "prj_project",
        [
            sa.Column("project_no", sa.String(32), nullable=False, comment="项目编号 PJ..."),
            sa.Column("name", sa.String(255), nullable=True, comment="项目名称"),
            sa.Column("customer_id", sa.BigInteger(), nullable=True),
            sa.Column("customer_name", sa.String(128), nullable=True),
            sa.Column("contract_id", sa.BigInteger(), nullable=True),
            sa.Column("contract_no", sa.String(32), nullable=True),
            sa.Column("manager_id", sa.BigInteger(), nullable=True, comment="项目经理"),
            sa.Column("manager_name", sa.String(64), nullable=True),
            sa.Column("dept_id", sa.BigInteger(), nullable=True),
            sa.Column("dept_name", sa.String(64), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True, comment="计划开始"),
            sa.Column("end_date", sa.Date(), nullable=True, comment="计划完成"),
            sa.Column("status", sa.String(16), nullable=True, comment="draft/planning/executing/accepting/closed/cancelled"),
            sa.Column("progress", sa.Integer(), nullable=True, comment="整体进度百分比"),
            sa.Column("budget_amount", sa.Numeric(14, 2), nullable=True, comment="预算金额"),
            sa.Column("actual_amount", sa.Numeric(14, 2), nullable=True, comment="实际发生额"),
            sa.Column("description", sa.Text(), nullable=True, comment="项目说明"),
            sa.Column("remark", sa.String(500), nullable=True),
        ],
        [
            {"name": "ix_prj_project_project_no", "cols": ["project_no"], "unique": True},
            {"name": "ix_prj_project_name", "cols": ["name"]},
            {"name": "ix_prj_project_customer_id", "cols": ["customer_id"]},
            {"name": "ix_prj_project_customer_name", "cols": ["customer_name"]},
            {"name": "ix_prj_project_contract_id", "cols": ["contract_id"]},
            {"name": "ix_prj_project_manager_id", "cols": ["manager_id"]},
            {"name": "ix_prj_project_dept_id", "cols": ["dept_id"]},
            {"name": "ix_prj_project_start_date", "cols": ["start_date"]},
            {"name": "ix_prj_project_end_date", "cols": ["end_date"]},
            {"name": "ix_prj_project_status", "cols": ["status"]},
        ],
    )

    # ---------------- 项目任务（甘特行） ----------------
    _create(
        "prj_project_task",
        [
            sa.Column("project_id", sa.BigInteger(), nullable=False, comment="所属项目 prj_project.id"),
            sa.Column("task_id", sa.BigInteger(), nullable=True, comment="关联 task_task.id"),
            sa.Column("task_no", sa.String(32), nullable=True),
            sa.Column("task_name", sa.String(255), nullable=True),
            sa.Column("seq", sa.Integer(), nullable=True, comment="序号 / 排序"),
            sa.Column("group_code", sa.String(32), nullable=True, comment="sim/model/test/outsource"),
            sa.Column("owner_id", sa.BigInteger(), nullable=True),
            sa.Column("owner_name", sa.String(64), nullable=True),
            sa.Column("start_date", sa.Date(), nullable=True),
            sa.Column("end_date", sa.Date(), nullable=True),
            sa.Column("progress", sa.Integer(), nullable=True, comment="进度百分比"),
            sa.Column("milestone", sa.Integer(), nullable=True, comment="是否里程碑"),
            sa.Column("weight", sa.Numeric(8, 2), nullable=True, comment="权重（进度加权）"),
            sa.Column("status", sa.String(16), nullable=True, comment="pending/doing/done/delayed"),
            sa.Column("depends_on", sa.String(255), nullable=True, comment="前置项目任务 id，逗号分隔"),
            sa.Column("source", sa.String(8), nullable=True, comment="auto / manual"),
            sa.Column("remark", sa.String(500), nullable=True),
        ],
        [
            {"name": "ix_prj_project_task_project_id", "cols": ["project_id"]},
            {"name": "ix_prj_project_task_task_id", "cols": ["task_id"]},
            {"name": "ix_prj_project_task_task_no", "cols": ["task_no"]},
            {"name": "ix_prj_project_task_group_code", "cols": ["group_code"]},
            {"name": "ix_prj_project_task_owner_id", "cols": ["owner_id"]},
            {"name": "ix_prj_project_task_status", "cols": ["status"]},
        ],
        [{"name": "fk_prj_project_task_project", "column": "project_id", "target": "prj_project.id", "ondelete": "CASCADE"}],
    )


def downgrade() -> None:
    op.drop_index("ix_prj_project_task_status", table_name="prj_project_task")
    op.drop_index("ix_prj_project_task_owner_id", table_name="prj_project_task")
    op.drop_index("ix_prj_project_task_group_code", table_name="prj_project_task")
    op.drop_index("ix_prj_project_task_task_no", table_name="prj_project_task")
    op.drop_index("ix_prj_project_task_task_id", table_name="prj_project_task")
    op.drop_index("ix_prj_project_task_project_id", table_name="prj_project_task")
    op.drop_table("prj_project_task")

    op.drop_index("ix_prj_project_status", table_name="prj_project")
    op.drop_index("ix_prj_project_end_date", table_name="prj_project")
    op.drop_index("ix_prj_project_start_date", table_name="prj_project")
    op.drop_index("ix_prj_project_dept_id", table_name="prj_project")
    op.drop_index("ix_prj_project_manager_id", table_name="prj_project")
    op.drop_index("ix_prj_project_contract_id", table_name="prj_project")
    op.drop_index("ix_prj_project_customer_name", table_name="prj_project")
    op.drop_index("ix_prj_project_customer_id", table_name="prj_project")
    op.drop_index("ix_prj_project_name", table_name="prj_project")
    op.drop_index("ix_prj_project_project_no", table_name="prj_project")
    op.drop_table("prj_project")

    op.drop_index("ix_prd_schedule_status", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_plan_end", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_plan_start", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_resource_type", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_project_id", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_task_no", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_task_id", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_plan_id", table_name="prd_schedule")
    op.drop_index("ix_prd_schedule_schedule_no", table_name="prd_schedule")
    op.drop_table("prd_schedule")

    op.drop_index("ix_prd_plan_status", table_name="prd_plan")
    op.drop_index("ix_prd_plan_plan_no", table_name="prd_plan")
    op.drop_table("prd_plan")

    op.drop_index("ix_task_trace_node_code", table_name="task_trace")
    op.drop_index("ix_task_trace_task_id", table_name="task_trace")
    op.drop_table("task_trace")

    op.drop_index("ix_task_assignment_status", table_name="task_assignment")
    op.drop_index("ix_task_assignment_resource_id", table_name="task_assignment")
    op.drop_index("ix_task_assignment_dimension", table_name="task_assignment")
    op.drop_index("ix_task_assignment_task_id", table_name="task_assignment")
    op.drop_table("task_assignment")

    op.drop_index("ix_task_process_status", table_name="task_process")
    op.drop_index("ix_task_process_process_code", table_name="task_process")
    op.drop_index("ix_task_process_task_id", table_name="task_process")
    op.drop_table("task_process")

    op.drop_index("ix_task_task_role_group", table_name="task_task")
    op.drop_column("task_task", "compute_nodes")
    op.drop_column("task_task", "compute_cores")
    op.drop_column("task_task", "compute_resource")
    op.drop_column("task_task", "solver")
    op.drop_column("task_task", "mesh_count")
    op.drop_column("task_task", "process_stage")
    op.drop_column("task_task", "role_group")
    op.drop_column("task_task", "priority")
    op.drop_column("task_task", "progress")
    op.drop_column("task_task", "duration_hours")
    op.drop_column("task_task", "plan_start_date")
