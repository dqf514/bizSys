"""项目域的**事件联动**（F5）。

系统不是"记录工具"：任务一旦进入执行，项目就该自动从"策划中"推进到"执行中"，
而不是让人再去项目页面手工改一次状态。这类跨域联动统一走事件总线，
并且**每个联动都有独立开关**（管理员可在「流程与事件开关」面板逐项停用）。
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.common.events import DocumentStatusChanged, TaskAssigned, publish, subscribe, switch_key
from app.modules.project.models import Project, ProjectTask

# 开关：任务进入执行时自动推进项目状态
SWITCH_TASK_START = switch_key("TaskAssigned", "project.start")


def _on_task_assigned(event: TaskAssigned) -> None:
    """任务进入执行 → 关联项目由 planning 推进到 executing。"""
    db: Session = event.db
    rows = db.scalars(
        select(ProjectTask).where(
            ProjectTask.task_id == event.task_id,
            ProjectTask.deleted == 0,
        )
    ).all()
    for pt in rows:
        project = db.get(Project, pt.project_id)
        if not project or project.deleted:
            continue
        if project.status != "planning":
            continue
        project.status = "executing"
        project.version = (project.version or 0) + 1
        project.update_time = datetime.now()
        publish(
            DocumentStatusChanged(
                biz_type="project",
                biz_id=project.id,
                doc_label=f"{project.project_no} {project.name}",
                from_status="planning",
                to_status="executing",
                operator_id=event.operator_id,
                db=db,
            )
        )


def register_flow_handlers() -> None:
    """由 ``app.modules.approval.wiring.install()`` 显式装配。"""
    subscribe(TaskAssigned, _on_task_assigned, key=SWITCH_TASK_START, name="project.start_on_task")
