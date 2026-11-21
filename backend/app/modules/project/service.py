"""项目管理服务（B5 CSV 31）。

职责：
- 项目与项目任务的生命周期维护；
- **甘特数据推导**：按项目任务的起止日期 + 进度生成甘特行，里程碑单独标注；
- **自动生成甘特**：从任务输入（task_task）与已发布排程（prd_schedule）推导项目任务的
  起止日期与分组，形成"任务输入 → 排期 → 项目甘特"的闭环；
- 进度回写：项目整体进度 = 各项目任务按权重加权平均。
"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.project.models import Project, ProjectTask
from app.modules.task.models import Task

# 任务类型 → 项目任务分组（CSV 18：仿真 / 模型 / 试验 / 委外）
TYPE_TO_GROUP = {
    "sim": "sim",
    "simulation": "sim",
    "cfd": "sim",
    "model": "model",
    "modeling": "model",
    "test": "test",
    "windtunnel": "test",
    "wind_tunnel": "test",
    "testing": "test",
    "experiment": "test",
    "outsource": "outsource",
    "outsourcing": "outsource",
}

GROUP_CN = {
    "sim": "仿真",
    "model": "模型",
    "test": "试验",
    "outsource": "委外",
}


def group_of(task_type: str, fallback: str = "") -> str:
    key = (task_type or "").strip().lower()
    if key in TYPE_TO_GROUP:
        return TYPE_TO_GROUP[key]
    if fallback:
        return fallback
    return key


def recompute_progress(db: Session, project: Project) -> int:
    """项目整体进度 = 项目任务按权重加权平均（无权重时按任务数平均）。"""
    rows = db.scalars(
        select(ProjectTask).where(ProjectTask.project_id == project.id, ProjectTask.deleted == 0)
    ).all()
    if not rows:
        project.progress = 0
        return 0
    total_weight = sum(float(r.weight or 0) for r in rows)
    if total_weight > 0:
        acc = sum(float(r.weight or 0) * float(r.progress or 0) for r in rows)
        project.progress = int(round(acc / total_weight))
    else:
        project.progress = int(round(sum(float(r.progress or 0) for r in rows) / len(rows)))
    return project.progress


def task_dates(db: Session, task: Task) -> tuple[date | None, date | None]:
    """任务的计划起止日期；优先取已发布排程，其次取任务自身字段。"""
    from app.modules.production.models import ProdSchedule

    rows = db.execute(
        select(ProdSchedule.plan_start, ProdSchedule.plan_end)
        .where(
            ProdSchedule.task_id == task.id,
            ProdSchedule.deleted == 0,
            ProdSchedule.status.in_(("published", "confirmed")),
        )
        .order_by(ProdSchedule.plan_start)
    ).all()
    if rows:
        start = rows[0][0]
        end = rows[-1][1]
        return (start.date() if start else None), (end.date() if end else None)
    return task.plan_start_date, task.plan_finish_date


def sync_task_progress(db: Session, project_task: ProjectTask) -> None:
    """把业务任务的进度同步到项目任务（口径一致）。"""
    if not project_task.task_id:
        return
    task = db.get(Task, project_task.task_id)
    if not task or task.deleted:
        return
    project_task.progress = int(task.progress or 0)
    project_task.task_no = task.task_no or project_task.task_no
    project_task.task_name = task.task_name or project_task.task_name
    if not project_task.owner_id and task.owner_id:
        project_task.owner_id = task.owner_id
        project_task.owner_name = task.owner_name


def generate_tasks(
    db: Session,
    project: Project,
    tasks: list[Task],
    group_code: str = "",
    overwrite: bool = False,
) -> list[ProjectTask]:
    """按任务与排期自动生成项目任务（甘特行）。"""
    existing = {
        r.task_id: r
        for r in db.scalars(
            select(ProjectTask).where(
                ProjectTask.project_id == project.id,
                ProjectTask.deleted == 0,
                ProjectTask.task_id.is_not(None),
            )
        ).all()
    }
    created: list[ProjectTask] = []
    seq = len(existing)
    for task in tasks:
        row = existing.get(task.id)
        if row is None:
            row = ProjectTask(
                project_id=project.id,
                task_id=task.id,
                task_no=task.task_no or "",
                task_name=task.task_name,
                seq=seq,
                group_code=group_code or group_of(task.task_type),
                owner_id=task.owner_id,
                owner_name=task.owner_name,
                progress=int(task.progress or 0),
                weight=1,
                status="pending",
                source="auto",
            )
            db.add(row)
            created.append(row)
            seq += 1
        elif overwrite:
            row.group_code = group_code or row.group_code or group_of(task.task_type)
            row.source = "auto"
        start, end = task_dates(db, task)
        if start:
            row.start_date = start
        if end:
            row.end_date = end
        sync_task_progress(db, row)
        if row.progress >= 100:
            row.status = "done"
        elif row.progress > 0:
            row.status = "doing"
    db.flush()
    recompute_progress(db, project)
    db.flush()
    return created


def gantt_data(db: Session, project: Project) -> dict:
    """项目甘特数据：行（项目任务）+ 里程碑 + 汇总。"""
    rows = list(
        db.scalars(
            select(ProjectTask)
            .where(ProjectTask.project_id == project.id, ProjectTask.deleted == 0)
            .order_by(ProjectTask.seq, ProjectTask.id)
        ).all()
    )
    items = []
    for r in rows:
        items.append(
            {
                "id": r.id,
                "taskId": r.task_id,
                "taskNo": r.task_no,
                "taskName": r.task_name,
                "seq": r.seq,
                "groupCode": r.group_code,
                "groupText": GROUP_CN.get(r.group_code, r.group_code),
                "ownerId": r.owner_id,
                "ownerName": r.owner_name,
                "startDate": r.start_date.strftime("%Y-%m-%d") if r.start_date else "",
                "endDate": r.end_date.strftime("%Y-%m-%d") if r.end_date else "",
                "progress": r.progress,
                "milestone": bool(r.milestone),
                "weight": float(r.weight or 0),
                "status": r.status,
                "dependsOn": r.depends_on,
                "source": r.source,
                "remark": r.remark,
            }
        )
    milestones = [i for i in items if i["milestone"]]
    starts = [i["startDate"] for i in items if i["startDate"]]
    ends = [i["endDate"] for i in items if i["endDate"]]
    return {
        "projectId": project.id,
        "projectNo": project.project_no,
        "projectName": project.name,
        "status": project.status,
        "progress": project.progress,
        "startDate": project.start_date.strftime("%Y-%m-%d") if project.start_date else (min(starts) if starts else ""),
        "endDate": project.end_date.strftime("%Y-%m-%d") if project.end_date else (max(ends) if ends else ""),
        "items": items,
        "milestones": milestones,
        "total": len(items),
    }


def now() -> datetime:
    return datetime.now()
