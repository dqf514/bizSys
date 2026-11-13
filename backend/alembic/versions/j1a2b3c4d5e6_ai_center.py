"""AI 中心：ai_usage_log（网关用量日志）+ task_progress_log（任务拍照进度）

Revision ID: j1a2b3c4d5e6
Revises: i1a2b3c4d5e6
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "j1a2b3c4d5e6"
down_revision = "i1a2b3c4d5e6"
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
        "ai_usage_log",
        sa.Column("user_id", sa.BigInteger(), nullable=True, comment="调用用户"),
        sa.Column("user_name", sa.String(64), nullable=False, server_default=""),
        sa.Column("feature", sa.String(32), nullable=False, comment="quote/contract_ocr/task_photo/report_summary"),
        sa.Column("model", sa.String(64), nullable=False, server_default=""),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, comment="success/error/fallback"),
        sa.Column("error", sa.String(500), nullable=False, server_default=""),
        sa.Column("biz_type", sa.String(32), nullable=False, server_default=""),
        sa.Column("biz_id", sa.BigInteger(), nullable=True),
        sa.Column("prompt_version", sa.String(16), nullable=False, server_default=""),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_log_feature", "ai_usage_log", ["feature"])
    op.create_index("ix_ai_usage_log_status", "ai_usage_log", ["status"])
    op.create_index("ix_ai_usage_feature_time", "ai_usage_log", ["feature", "create_time"])
    op.create_index("ix_ai_usage_user_time", "ai_usage_log", ["user_id", "create_time"])

    op.create_table(
        "task_progress_log",
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.Column("percent", sa.Integer(), nullable=False, server_default="0", comment="完成百分比 0-100"),
        sa.Column("note", sa.Text(), nullable=True, comment="进度描述"),
        sa.Column("image_path", sa.String(255), nullable=False, server_default="", comment="现场照片相对路径"),
        sa.Column("source", sa.String(8), nullable=False, server_default="manual", comment="ai/manual"),
        sa.Column("operator_id", sa.BigInteger(), nullable=True),
        sa.Column("operator_name", sa.String(64), nullable=False, server_default=""),
        *_BASE_COLS,
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["task_id"], ["task_task.id"]),
    )
    op.create_index("ix_task_progress_log_task_id", "task_progress_log", ["task_id"])


def downgrade() -> None:
    op.drop_table("task_progress_log")
    op.drop_table("ai_usage_log")
