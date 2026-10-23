"""task_task 状态精简：assigning/assigned → in_progress，closed → finished

2026-10-21 迭代评审：任务主状态合并为
draft(创建待提交) / approving / rejected / in_progress(分配执行中) /
finished(已完成) / settled(已结算) / stopped(已停止)。

Revision ID: e5f6a7b8c9d0
Revises: d8e9f0a1b2c3
Create Date: 2026-10-25
"""
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE task_task SET status='in_progress' WHERE status IN ('assigning','assigned')")
    op.execute("UPDATE task_task SET status='finished' WHERE status='closed'")


def downgrade() -> None:
    # 无法区分合并前的粒度：in_progress 回退 assigning，finished 回退 closed
    op.execute("UPDATE task_task SET status='assigning' WHERE status='in_progress'")
    op.execute("UPDATE task_task SET status='closed' WHERE status='finished'")
