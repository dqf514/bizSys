"""工时填报业务逻辑：填报 CRUD / 状态流转 / 我的列表 / 三维度统计。

- 可填报任务口径：status=in_progress 且已关联合同（合同/客户快照落行）；
- 统计口径：仅 submitted 行计入汇总（草稿是未确认的私人记录）；
- 部门维度取自填报人主部门（sys_user.dept_id/dept_name 冗余）。
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.filters import apply_list_filters
from app.common.pagination import PageParams, page_result
from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.hr.models import HrTimesheet
from app.modules.hr.schemas import TimesheetIn
from app.modules.task.models import Task

FILLABLE_STATUS = "in_progress"


def _out(t: HrTimesheet) -> dict:
    return {
        "id": t.id,
        "userId": t.user_id,
        "userName": t.user_name,
        "workDate": t.work_date.strftime("%Y-%m-%d"),
        "taskId": t.task_id,
        "taskNo": t.task_no,
        "taskName": t.task_name,
        "contractId": t.contract_id,
        "contractNo": t.contract_no,
        "customerId": t.customer_id,
        "customerName": t.customer_name,
        "hours": float(t.hours),
        "content": t.content,
        "remark": t.remark,
        "status": t.status,
        "submittedAt": t.submitted_at.strftime("%Y-%m-%d %H:%M:%S") if t.submitted_at else "",
        "createTime": t.create_time.strftime("%Y-%m-%d %H:%M:%S") if t.create_time else "",
        "updateTime": t.update_time.strftime("%Y-%m-%d %H:%M:%S") if t.update_time else "",
    }


def _load(db: Session, tid: int) -> HrTimesheet:
    t = db.get(HrTimesheet, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return t


def _check_owner(t: HrTimesheet, current: User) -> None:
    if t.user_id != current.id:
        raise BizException(R.AUTH_FORBIDDEN, "仅本人可操作工时记录", http_status=403)


def _fillable_task(db: Session, task_id: int) -> Task:
    t = db.get(Task, task_id)
    if not t or t.deleted or t.status != FILLABLE_STATUS or not t.contract_id:
        raise BizException(R.HR_TASK_NOT_FILLABLE)
    return t


def _check_date(work_date: date) -> None:
    if work_date > date.today():
        raise BizException(R.HR_FUTURE_DATE)


def _check_dup(db: Session, user_id: int, work_date: date, task_id: int, exclude_id: int = 0) -> None:
    stmt = select(HrTimesheet).where(
        HrTimesheet.user_id == user_id,
        HrTimesheet.work_date == work_date,
        HrTimesheet.task_id == task_id,
        HrTimesheet.deleted == 0,
        HrTimesheet.id != exclude_id,
    )
    if db.scalar(stmt):
        raise BizException(R.HR_TIMESHEET_EXISTS)


def _apply(t: HrTimesheet, body: TimesheetIn, task: Task) -> None:
    t.task_id = body.task_id
    t.task_no = task.task_no or ""
    t.task_name = task.task_name
    t.contract_id = task.contract_id or 0
    t.contract_no = task.contract_no
    t.customer_id = task.customer_id or 0
    t.customer_name = task.customer_name
    t.work_date = body.work_date
    t.hours = body.hours
    t.content = body.content.strip()
    t.remark = body.remark.strip()


# ---------------- 填报（用户侧） ----------------


def create(db: Session, current: User, body: TimesheetIn) -> HrTimesheet:
    _check_date(body.work_date)
    task = _fillable_task(db, body.task_id)
    _check_dup(db, current.id, body.work_date, body.task_id)
    t = HrTimesheet(user_id=current.id, user_name=current.name or current.username)
    _apply(t, body, task)
    t.create_by = current.id
    if body.submit:
        t.status = "submitted"
        t.submitted_at = datetime.now()
    db.add(t)
    db.flush()
    return t


def update(db: Session, current: User, tid: int, body: TimesheetIn) -> HrTimesheet:
    t = _load(db, tid)
    _check_owner(t, current)
    if t.status != "draft":
        raise BizException(R.HR_TIMESHEET_INVALID_STATE, "已提交的工时只读，请先退回草稿")
    _check_date(body.work_date)
    task = _fillable_task(db, body.task_id)
    _check_dup(db, current.id, body.work_date, body.task_id, exclude_id=t.id)
    _apply(t, body, task)
    t.update_by = current.id
    if body.submit:
        t.status = "submitted"
        t.submitted_at = datetime.now()
    db.flush()
    return t


def submit(db: Session, current: User, tid: int) -> HrTimesheet:
    t = _load(db, tid)
    _check_owner(t, current)
    if t.status != "draft":
        raise BizException(R.HR_TIMESHEET_INVALID_STATE)
    t.status = "submitted"
    t.submitted_at = datetime.now()
    t.update_by = current.id
    db.flush()
    return t


def withdraw(db: Session, current: User, tid: int) -> HrTimesheet:
    t = _load(db, tid)
    _check_owner(t, current)
    if t.status != "submitted":
        raise BizException(R.HR_TIMESHEET_INVALID_STATE)
    t.status = "draft"
    t.update_by = current.id
    db.flush()
    return t


def remove(db: Session, current: User, tid: int) -> HrTimesheet:
    t = _load(db, tid)
    _check_owner(t, current)
    if t.status != "draft":
        raise BizException(R.HR_TIMESHEET_INVALID_STATE, "已提交的工时不可删除，请先退回草稿")
    # 软删写行 id：不与历史软删行撞 (user,date,task,deleted) 唯一键
    t.deleted = t.id
    t.update_by = current.id
    db.flush()
    return t


def day_entries(db: Session, current: User, day: date) -> dict:
    rows = db.scalars(
        select(HrTimesheet)
        .where(HrTimesheet.user_id == current.id, HrTimesheet.work_date == day, HrTimesheet.deleted == 0)
        .order_by(HrTimesheet.id)
    ).all()
    total = sum(Decimal(r.hours) for r in rows)
    return {"items": [_out(r) for r in rows], "totalHours": float(total)}


def week_summary(db: Session, current: User, any_day: date) -> dict:
    """所在周（周一至周日）逐日合计：填报页日期快选条用。"""
    monday = any_day - timedelta(days=any_day.weekday())
    days = [monday + timedelta(days=i) for i in range(7)]
    rows = db.execute(
        select(HrTimesheet.work_date, func.sum(HrTimesheet.hours), func.count())
        .where(
            HrTimesheet.user_id == current.id,
            HrTimesheet.work_date >= monday,
            HrTimesheet.work_date <= days[-1],
            HrTimesheet.deleted == 0,
        )
        .group_by(HrTimesheet.work_date)
    ).all()
    by_day = {d: (float(h or 0), c) for d, h, c in rows}
    return {
        "weekStart": monday.strftime("%Y-%m-%d"),
        "days": [
            {
                "date": d.strftime("%Y-%m-%d"),
                "totalHours": by_day.get(d, (0.0, 0))[0],
                "count": by_day.get(d, (0.0, 0))[1],
                "future": d > date.today(),
            }
            for d in days
        ],
    }


# ---------------- 填报选项（远程检索） ----------------


def options_contracts(db: Session, q: str) -> list[dict]:
    stmt = (
        select(Contract)
        .where(Contract.deleted == 0, Contract.status == "approved")
        .order_by(Contract.id.desc())
        .limit(20)
    )
    if q:
        stmt = stmt.where(or_(Contract.name.like(f"%{q}%"), Contract.contract_no.like(f"%{q}%")))
    rows = db.scalars(stmt).all()
    return [
        {
            "id": c.id,
            "contractNo": c.contract_no or "",
            "name": c.name,
            "customerName": c.customer_name,
        }
        for c in rows
    ]


def options_tasks(db: Session, contract_id: int, q: str) -> list[dict]:
    """某合同下可填报任务（进行中）；带客户名，供级联第二级远程检索。"""
    stmt = (
        select(Task)
        .where(Task.deleted == 0, Task.status == FILLABLE_STATUS, Task.contract_id == contract_id)
        .order_by(Task.id.desc())
        .limit(20)
    )
    if q:
        stmt = stmt.where(or_(Task.task_name.like(f"%{q}%"), Task.task_no.like(f"%{q}%")))
    rows = db.scalars(stmt).all()
    return [
        {
            "id": t.id,
            "taskNo": t.task_no or "",
            "taskName": t.task_name,
            "contractId": t.contract_id,
            "contractNo": t.contract_no,
            "customerName": t.customer_name,
        }
        for t in rows
    ]


# ---------------- 我的工时列表 ----------------


def my_list(db: Session, current: User, pp: PageParams, query_params) -> dict:
    stmt, total = apply_list_filters(
        select(HrTimesheet),
        HrTimesheet,
        query_params,
        db,
        pp,
        search_cols=["task_no", "task_name", "contract_no", "customer_name", "content"],
        range_cols={"work_date"},
        sort_cols={"work_date", "hours", "create_time", "update_time", "id"},
        default_sort=("work_date", "desc"),
        extra_where=[HrTimesheet.user_id == current.id],
    )
    rows = db.scalars(stmt).all()
    return page_result([_out(r) for r in rows], total, pp.page, pp.size)


def my_counts(db: Session, current: User) -> dict:
    rows = db.execute(
        select(HrTimesheet.status, func.count()).where(
            HrTimesheet.user_id == current.id, HrTimesheet.deleted == 0
        ).group_by(HrTimesheet.status)
    ).all()
    data = {"draft": 0, "submitted": 0}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


# ---------------- 统计（管理视角，仅 submitted 计入） ----------------


def _stats_where(date_start: date | None, date_end: date | None, dept_id: int, user_id: int, task_id: int) -> list:
    conds = [HrTimesheet.deleted == 0, HrTimesheet.status == "submitted"]
    if date_start:
        conds.append(HrTimesheet.work_date >= date_start)
    if date_end:
        conds.append(HrTimesheet.work_date <= date_end)
    if user_id:
        conds.append(HrTimesheet.user_id == user_id)
    if task_id:
        conds.append(HrTimesheet.task_id == task_id)
    if dept_id:
        conds.append(HrTimesheet.user_id.in_(select(User.id).where(User.dept_id == dept_id, User.deleted == 0)))
    return conds


def stats(
    db: Session,
    dimension: str,
    date_start: date | None,
    date_end: date | None,
    dept_id: int,
    user_id: int,
    task_id: int,
) -> dict:
    conds = _stats_where(date_start, date_end, dept_id, user_id, task_id)
    total_hours = func.coalesce(func.sum(HrTimesheet.hours), 0)
    if dimension == "task":
        stmt = (
            select(
                HrTimesheet.task_id,
                HrTimesheet.task_no,
                HrTimesheet.task_name,
                HrTimesheet.contract_no,
                HrTimesheet.customer_name,
                total_hours.label("hours"),
                func.count().label("entries"),
                func.count(func.distinct(HrTimesheet.user_id)).label("users"),
            )
            .where(*conds)
            .group_by(
                HrTimesheet.task_id,
                HrTimesheet.task_no,
                HrTimesheet.task_name,
                HrTimesheet.contract_no,
                HrTimesheet.customer_name,
            )
        )
        rows = [
            {
                "taskId": r.task_id,
                "taskNo": r.task_no,
                "taskName": r.task_name,
                "contractNo": r.contract_no,
                "customerName": r.customer_name,
                "totalHours": float(r.hours),
                "entryCount": r.entries,
                "userCount": r.users,
            }
            for r in db.execute(stmt).all()
        ]
    elif dimension == "contract":
        stmt = (
            select(
                HrTimesheet.contract_id,
                HrTimesheet.contract_no,
                HrTimesheet.customer_name,
                total_hours.label("hours"),
                func.count().label("entries"),
                func.count(func.distinct(HrTimesheet.user_id)).label("users"),
                func.count(func.distinct(HrTimesheet.task_id)).label("tasks"),
            )
            .where(*conds)
            .group_by(HrTimesheet.contract_id, HrTimesheet.contract_no, HrTimesheet.customer_name)
        )
        rows = [
            {
                "contractId": r.contract_id,
                "contractNo": r.contract_no,
                "customerName": r.customer_name,
                "totalHours": float(r.hours),
                "entryCount": r.entries,
                "userCount": r.users,
                "taskCount": r.tasks,
            }
            for r in db.execute(stmt).all()
        ]
    else:  # user
        stmt = (
            select(
                HrTimesheet.user_id,
                HrTimesheet.user_name,
                func.coalesce(func.max(User.dept_name), "").label("dept_name"),
                total_hours.label("hours"),
                func.count().label("entries"),
                func.count(func.distinct(HrTimesheet.task_id)).label("tasks"),
                func.count(func.distinct(HrTimesheet.work_date)).label("days"),
            )
            .outerjoin(User, User.id == HrTimesheet.user_id)
            .where(*conds)
            .group_by(HrTimesheet.user_id, HrTimesheet.user_name)
        )
        rows = [
            {
                "userId": r.user_id,
                "userName": r.user_name,
                "deptName": r.dept_name,
                "totalHours": float(r.hours),
                "entryCount": r.entries,
                "taskCount": r.tasks,
                "dayCount": r.days,
            }
            for r in db.execute(stmt).all()
        ]
    rows.sort(key=lambda x: -x["totalHours"])
    return {"dimension": dimension, "rows": rows, "grandTotalHours": sum(r["totalHours"] for r in rows)}


def stats_detail(
    db: Session,
    user_id: int,
    pp: PageParams,
    date_start: date | None,
    date_end: date | None,
    task_id: int,
) -> dict:
    """人员下钻：某人的工时明细（仅 submitted，与汇总口径一致）。"""
    conds = _stats_where(date_start, date_end, 0, user_id, task_id)
    total = db.scalar(select(func.count()).select_from(HrTimesheet).where(*conds)) or 0
    rows = db.scalars(
        select(HrTimesheet)
        .where(*conds)
        .order_by(HrTimesheet.work_date.desc(), HrTimesheet.id.desc())
        .offset((pp.page - 1) * pp.size)
        .limit(pp.size)
    ).all()
    return page_result([_out(r) for r in rows], total, pp.page, pp.size)


def stats_options(db: Session, kind: str, q: str) -> list[dict]:
    """统计筛选项远程检索：dept（有工时人员的部门）/ user（有工时人员）/ task（全部任务）。"""
    if kind == "dept":
        stmt = (
            select(User.dept_id, func.max(User.dept_name))
            .where(User.dept_id.isnot(None), User.deleted == 0, User.id.in_(_ts_user_ids()))
            .group_by(User.dept_id)
            .order_by(User.dept_id)
        )
        rows = db.execute(stmt).all()
        return [{"id": d, "label": n or ""} for d, n in rows]
    if kind == "user":
        stmt = select(User).where(User.deleted == 0, User.id.in_(_ts_user_ids())).order_by(User.id).limit(20)
        if q:
            stmt = stmt.where(or_(User.name.like(f"%{q}%"), User.username.like(f"%{q}%")))
        return [
            {"id": u.id, "label": u.name or u.username, "deptName": u.dept_name}
            for u in db.scalars(stmt).all()
        ]
    # task
    stmt = select(Task).where(Task.deleted == 0).order_by(Task.id.desc()).limit(20)
    if q:
        stmt = stmt.where(or_(Task.task_name.like(f"%{q}%"), Task.task_no.like(f"%{q}%")))
    return [
        {"id": t.id, "label": f"{t.task_no or ''} {t.task_name}".strip(), "contractNo": t.contract_no}
        for t in db.scalars(stmt).all()
    ]


def _ts_user_ids():
    return select(HrTimesheet.user_id).where(HrTimesheet.deleted == 0).distinct().scalar_subquery()
