"""人事行政路由 /api/v1/hr：工时填报（用户侧）+ 工时统计（管理视角）。

权限：hr:timesheet:create（填报/流转）· hr:timesheet:list（我的列表/导出）
     · hr:timesheet:stats（统计/下钻）· hr:timesheet:stats:export（统计导出）。
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.common.audit import record
from app.common.pagination import PAGE_MAX, PageParams
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.hr import schemas as S
from app.modules.hr import service as svc
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/hr", tags=["hr"], route_class=EnvelopeRoute)

STATUS_CN = {"draft": "草稿", "submitted": "已提交"}

MY_EXPORT_COLS = [
    {"key": "workDate", "label": "日期", "width": 12},
    {"key": "taskNo", "label": "任务编号", "width": 18},
    {"key": "taskName", "label": "任务名称", "width": 32},
    {"key": "contractNo", "label": "合同号", "width": 18},
    {"key": "customerName", "label": "客户", "width": 24},
    {"key": "hours", "label": "工时(h)", "width": 9},
    {"key": "content", "label": "工作内容", "width": 40},
    {"key": "remark", "label": "备注", "width": 20},
    {"key": "status", "label": "状态", "width": 10},
    {"key": "submittedAt", "label": "提交时间", "width": 19},
]

STATS_EXPORT_COLS = {
    "task": [
        {"key": "taskNo", "label": "任务编号", "width": 18},
        {"key": "taskName", "label": "任务名称", "width": 32},
        {"key": "contractNo", "label": "合同号", "width": 18},
        {"key": "customerName", "label": "客户", "width": 24},
        {"key": "totalHours", "label": "工时合计(h)", "width": 12},
        {"key": "entryCount", "label": "填报条数", "width": 10},
        {"key": "userCount", "label": "人数", "width": 8},
    ],
    "contract": [
        {"key": "contractNo", "label": "合同号", "width": 18},
        {"key": "customerName", "label": "客户", "width": 24},
        {"key": "totalHours", "label": "工时合计(h)", "width": 12},
        {"key": "entryCount", "label": "填报条数", "width": 10},
        {"key": "userCount", "label": "人数", "width": 8},
        {"key": "taskCount", "label": "任务数", "width": 8},
    ],
    "user": [
        {"key": "userName", "label": "姓名", "width": 14},
        {"key": "deptName", "label": "部门", "width": 16},
        {"key": "totalHours", "label": "工时合计(h)", "width": 12},
        {"key": "entryCount", "label": "填报条数", "width": 10},
        {"key": "taskCount", "label": "任务数", "width": 8},
        {"key": "dayCount", "label": "填报天数", "width": 10},
    ],
}


# ---------------- 填报（用户侧） ----------------


@router.get("/timesheets/options/contracts")
def option_contracts(
    q: str = Query("", max_length=64),
    current: User = Depends(require_perm("hr:timesheet:create")),
    db: Session = Depends(get_db),
):
    """合同远程检索（仅 approved，任务必须挂合同）。"""
    return svc.options_contracts(db, q.strip())


@router.get("/timesheets/options/tasks")
def option_tasks(
    contract_id: int = Query(alias="contractId"),
    q: str = Query("", max_length=64),
    current: User = Depends(require_perm("hr:timesheet:create")),
    db: Session = Depends(get_db),
):
    """合同下可填报任务远程检索（进行中）。"""
    return svc.options_tasks(db, contract_id, q.strip())


@router.get("/timesheets/day")
def day(
    date_: date = Query(alias="date"),
    current: User = Depends(require_perm("hr:timesheet:create")),
    db: Session = Depends(get_db),
):
    """某日我的工时明细 + 当日合计。"""
    return svc.day_entries(db, current, date_)


@router.get("/timesheets/week")
def week(
    date_: date = Query(alias="date"),
    current: User = Depends(require_perm("hr:timesheet:create")),
    db: Session = Depends(get_db),
):
    """所在周逐日合计（日期快选条）。"""
    return svc.week_summary(db, current, date_)


@router.post("/timesheets/ai-prefill")
def ai_prefill(
    body: S.TimesheetPrefillIn,
    current: User = Depends(require_perm("hr:timesheet:create")),
    db: Session = Depends(get_db),
):
    """AI 预填当日工时草稿（不落库）：按任务近期进度日志 + 本人近期工时生成建议。"""
    from app.modules.hr import ai_prefill as ai_prefill_svc

    return ai_prefill_svc.ai_prefill(db, current, body.task_id, body.work_date)


@router.post("/timesheets", status_code=201)
def create(
    body: S.TimesheetIn,
    current: User = Depends(require_perm("hr:timesheet:create")),
    db: Session = Depends(get_db),
):
    t = svc.create(db, current, body)
    record(db, user_id=current.id, module="hr", action="hr_timesheet_create", biz_type="hr_timesheet", biz_id=t.id,
           detail={"workDate": body.work_date.isoformat(), "taskId": body.task_id, "submit": body.submit})
    db.commit()
    return svc._out(t)


@router.put("/timesheets/{tid}")
def update(
    tid: int,
    body: S.TimesheetIn,
    current: User = Depends(require_perm("hr:timesheet:create")),
    db: Session = Depends(get_db),
):
    t = svc.update(db, current, tid, body)
    record(db, user_id=current.id, module="hr", action="hr_timesheet_update", biz_type="hr_timesheet", biz_id=tid,
           detail={"workDate": body.work_date.isoformat(), "submit": body.submit})
    db.commit()
    return svc._out(t)


@router.delete("/timesheets/{tid}")
def delete(tid: int, current: User = Depends(require_perm("hr:timesheet:create")), db: Session = Depends(get_db)):
    svc.remove(db, current, tid)
    record(db, user_id=current.id, module="hr", action="hr_timesheet_delete", biz_type="hr_timesheet", biz_id=tid)
    db.commit()
    return None


@router.post("/timesheets/{tid}/submit")
def submit(tid: int, current: User = Depends(require_perm("hr:timesheet:create")), db: Session = Depends(get_db)):
    t = svc.submit(db, current, tid)
    record(db, user_id=current.id, module="hr", action="hr_timesheet_submit", biz_type="hr_timesheet", biz_id=tid)
    db.commit()
    return svc._out(t)


@router.post("/timesheets/{tid}/withdraw")
def withdraw(tid: int, current: User = Depends(require_perm("hr:timesheet:create")), db: Session = Depends(get_db)):
    """退回草稿（本人撤回已提交工时）。"""
    t = svc.withdraw(db, current, tid)
    record(db, user_id=current.id, module="hr", action="hr_timesheet_withdraw", biz_type="hr_timesheet", biz_id=tid)
    db.commit()
    return svc._out(t)


# ---------------- 我的工时列表 ----------------


@router.get("/timesheets/my")
def my(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:timesheet:list")),
    db: Session = Depends(get_db),
):
    return svc.my_list(db, current, PageParams(page=page, size=size), request.query_params)


@router.get("/timesheets/my/counts")
def my_counts(current: User = Depends(require_perm("hr:timesheet:list")), db: Session = Depends(get_db)):
    return svc.my_counts(db, current)


@router.get("/timesheets/my/export")
def my_export(
    request: Request,
    current: User = Depends(require_perm("hr:timesheet:list")),
    db: Session = Depends(get_db),
):
    """我的工时导出（沿用列表权限，复用 my 过滤，分页拉全）。"""
    rows = []
    total = None
    page = 1
    while total is None or len(rows) < total:
        data = svc.my_list(db, current, PageParams(page=page, size=200), request.query_params)
        total = data["total"]
        for item in data["items"]:
            item = dict(item)
            item["status"] = STATUS_CN.get(item["status"], item["status"])
            rows.append(item)
        if not data["items"] or page > 500:  # 防呆上限 10 万行
            break
        page += 1
    payload = export_xlsx_styled(rows, MY_EXPORT_COLS, "hr_my_timesheets")
    record(db, user_id=current.id, module="hr", action="hr_timesheet_export", detail={"count": len(rows)})
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('hr_my_timesheets')}"},
    )


# ---------------- 统计（管理视角） ----------------


@router.get("/timesheets/stats")
def stats(
    dimension: str = Query("user", pattern="^(task|contract|user)$"),
    date_start: date | None = Query(None, alias="dateStart"),
    date_end: date | None = Query(None, alias="dateEnd"),
    dept_id: int = Query(0, alias="deptId"),
    user_id: int = Query(0, alias="userId"),
    task_id: int = Query(0, alias="taskId"),
    current: User = Depends(require_perm("hr:timesheet:stats")),
    db: Session = Depends(get_db),
):
    """三维度汇总（task/contract/user），仅 submitted 计入。"""
    return svc.stats(db, dimension, date_start, date_end, dept_id, user_id, task_id)


@router.get("/timesheets/stats/detail")
def stats_detail(
    user_id: int = Query(alias="userId"),
    date_start: date | None = Query(None, alias="dateStart"),
    date_end: date | None = Query(None, alias="dateEnd"),
    task_id: int = Query(0, alias="taskId"),
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    current: User = Depends(require_perm("hr:timesheet:stats")),
    db: Session = Depends(get_db),
):
    """人员下钻：某人提交工时明细。"""
    return svc.stats_detail(db, user_id, PageParams(page=page, size=size), date_start, date_end, task_id)


@router.get("/timesheets/stats/options")
def stats_options(
    kind: str = Query(pattern="^(dept|user|task)$"),
    q: str = Query("", max_length=64),
    current: User = Depends(require_perm("hr:timesheet:stats")),
    db: Session = Depends(get_db),
):
    return svc.stats_options(db, kind, q.strip())


@router.get("/timesheets/stats/export")
def stats_export(
    dimension: str = Query("user", pattern="^(task|contract|user)$"),
    date_start: date | None = Query(None, alias="dateStart"),
    date_end: date | None = Query(None, alias="dateEnd"),
    dept_id: int = Query(0, alias="deptId"),
    user_id: int = Query(0, alias="userId"),
    task_id: int = Query(0, alias="taskId"),
    current: User = Depends(require_perm("hr:timesheet:stats:export")),
    db: Session = Depends(get_db),
):
    data = svc.stats(db, dimension, date_start, date_end, dept_id, user_id, task_id)
    rows = [dict(r) for r in data["rows"]]
    payload = export_xlsx_styled(rows, STATS_EXPORT_COLS[dimension], f"hr_timesheet_stats_{dimension}")
    record(db, user_id=current.id, module="hr", action="hr_timesheet_stats_export",
           detail={"dimension": dimension, "count": len(rows)})
    db.commit()
    filename = now_filename(f"hr_timesheet_stats_{dimension}")
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
