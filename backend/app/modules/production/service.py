"""智能排程服务（B5 CSV 22）。

排程算法：**规则式贪心**（不引入求解器）。

1. 取待排任务（可指定 task_ids / project_id / 时间窗），按「优先级升序 → 计划开始日升序」排序；
2. 对每个任务，收集其 **人 / 机 / 样车** 分配（时段独占资源）与 **物料** 分配（数量占用）；
3. 物料先做库存可用量校验，不足则该任务标记为冲突（conflict）并给出原因；
4. 在「不与已占用时段冲突」的前提下，自最早可行时间起顺延，求出该任务的排期窗口；
5. 生成方案（prd_plan）+ 排程行（prd_schedule），状态 scheduled（草稿）；
6. 人工可调整排程行（资源 / 时间 / 数量）后**发布**方案，发布时二次校验冲突，
   并把排期回写到任务的 plan_start_date / plan_finish_date。

资源占用模型：
- 时段独占（equipment / person / vehicle）：同一资源同一时间只允许一段占用；
- 数量占用（material）：按库存可用量校验，缺料即冲突。
"""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.asset.models import Item, StockLedger
from app.modules.production.models import ProdPlan, ProdSchedule
from app.modules.task.models import Task, TaskAssignment
from app.services.numbering import next_no

# 时段独占的资源维度
EXCLUSIVE_DIMS = ("equipment", "person", "vehicle")
# 数量占用的资源维度
QUANTITY_DIMS = ("material",)

DEFAULT_WORK_START = 9  # 09:00 起排
SLOT_STEP_HOURS = 1  # 冲突顺延步长（小时）
MAX_SHIFT_ITER = 24 * 60  # 最多顺延 60 天，避免死循环


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _as_datetime(d: date | None, base: date) -> datetime:
    return datetime.combine(d or base, datetime.min.time()).replace(hour=DEFAULT_WORK_START)


def _ceil_hour(dt: datetime) -> datetime:
    """冲突顺延时对齐到整点，避免出现 09:37 这种碎片时间。"""
    if dt.minute or dt.second:
        dt = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return dt


def occupied_map(
    db: Session, exclude_plan_id: int | None = None
) -> dict[tuple[str, int], list[tuple[datetime, datetime]]]:
    """已占用的 (资源类型, 资源 id) → 时段列表。

    只统计已发布 / 已确认的排程行 —— 草稿方案内的调整不应该互相阻挡。
    """
    stmt = select(ProdSchedule).where(
        ProdSchedule.deleted == 0,
        ProdSchedule.status.in_(("published", "confirmed")),
    )
    if exclude_plan_id:
        stmt = stmt.where(ProdSchedule.plan_id != exclude_plan_id)
    out: dict[tuple[str, int], list[tuple[datetime, datetime]]] = {}
    for row in db.scalars(stmt).all():
        if row.resource_id is None:
            continue
        if row.resource_type not in EXCLUSIVE_DIMS:
            continue  # 物料是数量占用，不占时段
        out.setdefault((row.resource_type, row.resource_id), []).append((row.plan_start, row.plan_end))
    return out


def on_hand_map(db: Session, item_ids: list[int]) -> dict[int, float]:
    """存货结存：入库累计 − 出库累计。"""
    if not item_ids:
        return {}
    rows = db.execute(
        select(
            StockLedger.item_id,
            StockLedger.direction,
            StockLedger.quantity,
        ).where(StockLedger.item_id.in_(item_ids), StockLedger.deleted == 0)
    ).all()
    result: dict[int, float] = {}
    for item_id, direction, qty in rows:
        sign = 1 if direction == "in" else -1
        result[item_id] = result.get(item_id, 0.0) + sign * _f(qty)
    return result


def item_map(db: Session, item_ids: list[int]) -> dict[int, Item]:
    if not item_ids:
        return {}
    return {i.id: i for i in db.scalars(select(Item).where(Item.id.in_(item_ids))).all()}


def task_assignments(db: Session, task_ids: list[int]) -> dict[int, list[TaskAssignment]]:
    """任务 → 其人/机/料/样车分配。"""
    if not task_ids:
        return {}
    rows = db.scalars(
        select(TaskAssignment).where(
            TaskAssignment.task_id.in_(task_ids),
            TaskAssignment.deleted == 0,
            TaskAssignment.dimension.in_(EXCLUSIVE_DIMS + QUANTITY_DIMS),
        )
    ).all()
    out: dict[int, list[TaskAssignment]] = {}
    for row in rows:
        out.setdefault(row.task_id, []).append(row)
    return out


def pick_tasks(
    db: Session,
    task_ids: list[int] | None = None,
    project_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    statuses: tuple[str, ...] = ("draft", "in_progress"),
) -> list[Task]:
    """待排任务集合。默认取未完成且已排入排程的任务状态。"""
    stmt = select(Task).where(Task.deleted == 0, Task.status.in_(statuses))
    if task_ids:
        stmt = stmt.where(Task.id.in_(task_ids))
    if project_id:
        # 项目任务挂接在 prj_project_task 上，这里通过任务号反查
        from app.modules.project.models import ProjectTask

        pids = db.scalars(
            select(ProjectTask.task_id).where(
                ProjectTask.project_id == project_id,
                ProjectTask.deleted == 0,
                ProjectTask.task_id.is_not(None),
            )
        ).all()
        stmt = stmt.where(Task.id.in_(pids or [-1]))
    if date_from:
        stmt = stmt.where(
            (Task.plan_finish_date.is_(None)) | (Task.plan_finish_date >= date_from)
        )
    if date_to:
        stmt = stmt.where(
            (Task.plan_start_date.is_(None)) | (Task.plan_start_date <= date_to)
        )
    tasks = list(db.scalars(stmt).all())
    # 优先级数字越小越优先；再按计划开始日；最后按 id 保证稳定
    return sorted(tasks, key=lambda t: (t.priority or 5, t.plan_start_date or date.max, t.id))


def find_slot(
    earliest: datetime,
    duration_hours: float,
    resources: list[TaskAssignment],
    occupied: dict[tuple[str, int], list[tuple[datetime, datetime]]],
) -> tuple[datetime, datetime, list[str]]:
    """贪心求最早可行时段。

    返回 (开始, 结束, 冲突说明列表)。**只有在顺延到上限仍找不到空档时**冲突说明才非空，
    调用方据此标记 conflict —— 能够通过顺延避开冲突属于正常排期，不算冲突。
    """
    start = _ceil_hour(earliest)
    duration = timedelta(hours=max(duration_hours, 0.5))
    notes: list[str] = []
    for _ in range(MAX_SHIFT_ITER):
        end = start + duration
        blocked_until: datetime | None = None
        blocker_name = ""
        for a in resources:
            if a.resource_id is None:
                continue
            for (s, e) in occupied.get((a.dimension, a.resource_id), []):
                if s < end and start < e:  # 区间重叠
                    if blocked_until is None or e > blocked_until:
                        blocked_until = e
                        blocker_name = a.resource_name or a.resource_code or str(a.resource_id)
        if blocked_until is None:
            return start, end, []  # 找到空档：顺延成功，不算冲突
        notes.append(f"资源 {blocker_name} 时段冲突")
        start = _ceil_hour(blocked_until)
        if len(notes) > 20:
            break
    return start, start + duration, notes or ["超过顺延上限，未能避开资源冲突"]


def generate_plan(
    db: Session,
    tasks: list[Task],
    name: str,
    base_date: date,
    user,
    plan_no: str = "",
) -> tuple[ProdPlan, list[ProdSchedule]]:
    """生成排程方案（草稿）。单号必须在入库前取好 —— plan_no / schedule_no 是唯一键。"""
    plan = ProdPlan(
        plan_no=plan_no or next_no(db, "production_plan"),
        name=name,
        plan_date=base_date,
        status="draft",
        auto_generated=1,
        task_count=len(tasks),
        generated_by=getattr(user, "id", None),
        generated_by_name=getattr(user, "name", "") or "",
    )
    db.add(plan)
    db.flush()

    assignments = task_assignments(db, [t.id for t in tasks])
    material_ids = [
        a.resource_id
        for rows in assignments.values()
        for a in rows
        if a.dimension == "material" and a.resource_id
    ]
    stock = on_hand_map(db, material_ids)
    items = item_map(db, material_ids)

    occupied = occupied_map(db)
    created: list[ProdSchedule] = []
    seq = 0
    conflict_count = 0
    for task in tasks:
        rows = assignments.get(task.id, [])
        exclusive = [a for a in rows if a.dimension in EXCLUSIVE_DIMS]
        materials = [a for a in rows if a.dimension in QUANTITY_DIMS]
        duration = _f(task.duration_hours) or 8.0
        earliest = _as_datetime(task.plan_start_date, base_date)
        start, end, notes = find_slot(earliest, duration, exclusive, occupied)

        shortage: list[str] = []
        for a in materials:
            if a.resource_id is None:
                continue
            available = stock.get(a.resource_id, 0.0)
            need = _f(a.qty)
            if need > available:
                item = items.get(a.resource_id)
                name_txt = item.name if item else (a.resource_name or str(a.resource_id))
                shortage.append(f"物料 {name_txt} 缺料（需 {need}{a.unit or ''}，可用 {available}{a.unit or ''}）")
        # 时段冲突只影响独占型资源（人 / 机 / 样车），缺料只影响物料行；
        # 任务级冲突计数按任务去重。
        time_conflict = bool(notes)
        status = "conflict" if time_conflict else "scheduled"
        reason = "；".join(shortage or notes)
        if time_conflict or shortage:
            conflict_count += 1

        for a in exclusive:
            seq += 1
            row = ProdSchedule(
                schedule_no=next_no(db, "production_schedule"),
                plan_id=plan.id,
                plan_no_text=plan.plan_no,
                task_id=task.id,
                task_no=task.task_no or "",
                task_name=task.task_name,
                resource_type=a.dimension,
                resource_id=a.resource_id,
                resource_code=a.resource_code or "",
                resource_name=a.resource_name or "",
                quantity=_f(a.qty),
                unit=a.unit or "",
                plan_start=start,
                plan_end=end,
                duration_hours=duration,
                priority=task.priority or 5,
                seq=seq,
                status=status,
                source="auto",
                conflict_reason=reason,
            )
            db.add(row)
            created.append(row)
            if a.resource_id is not None and not time_conflict:
                occupied.setdefault((a.dimension, a.resource_id), []).append((start, end))
        for a in materials:
            seq += 1
            row = ProdSchedule(
                schedule_no=next_no(db, "production_schedule"),
                plan_id=plan.id,
                plan_no_text=plan.plan_no,
                task_id=task.id,
                task_no=task.task_no or "",
                task_name=task.task_name,
                resource_type="material",
                resource_id=a.resource_id,
                resource_code=a.resource_code or "",
                resource_name=a.resource_name or "",
                quantity=_f(a.qty),
                unit=a.unit or "",
                plan_start=start,
                plan_end=end,
                duration_hours=duration,
                priority=task.priority or 5,
                seq=seq,
                status="conflict" if shortage else "scheduled",
                source="auto",
                conflict_reason="；".join(shortage),
            )
            db.add(row)
            created.append(row)

    plan.conflict_count = conflict_count
    db.flush()
    return plan, created


def detect_conflicts(rows: list[ProdSchedule]) -> list[str]:
    """同一资源时段重叠检测（用于发布前校验）。

    物料是数量占用而非时段独占，不参与重叠检测。
    """
    by_resource: dict[tuple[str, int], list[ProdSchedule]] = {}
    for r in rows:
        if r.resource_id is None:
            continue
        if r.resource_type not in EXCLUSIVE_DIMS:
            continue
        by_resource.setdefault((r.resource_type, r.resource_id), []).append(r)
    problems: list[str] = []
    for (rtype, rid), group in by_resource.items():
        group.sort(key=lambda x: x.plan_start)
        for i in range(1, len(group)):
            prev, cur = group[i - 1], group[i]
            if cur.plan_start < prev.plan_end:
                problems.append(
                    f"{rtype}:{rid} {cur.task_name or cur.task_no} 与 {prev.task_name or prev.task_no} 时段重叠"
                )
    return problems


def write_back_task_dates(db: Session, rows: list[ProdSchedule]) -> None:
    """把已发布排期回写到任务的计划开始 / 完成日期（排程与任务口径一致）。"""
    by_task: dict[int, list[ProdSchedule]] = {}
    for r in rows:
        if r.task_id:
            by_task.setdefault(r.task_id, []).append(r)
    for task_id, group in by_task.items():
        task = db.get(Task, task_id)
        if not task or task.deleted:
            continue
        start = min(g.plan_start for g in group).date()
        end = max(g.plan_end for g in group).date()
        task.plan_start_date = start
        task.plan_finish_date = end
    db.flush()
