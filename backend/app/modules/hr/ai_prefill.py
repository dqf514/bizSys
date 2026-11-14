"""AI 工时预填：任务近期进度日志 + 本人近期工时 → 当日工时数与工作内容草稿。

仅返回草稿（不落库），由人工在填报行上修改后随正常保存/提交落库；
hours 服务端 0.5 步进取整并 clamp 到 [0.5, 24]，content 截 500 字。
"""

import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.auth.models import User
from app.modules.hr.models import HrTimesheet
from app.modules.hr.service import _check_date, _fillable_task
from app.modules.task.models import TaskProgressLog

PREFILL_PROMPT_VERSION = "v1"

PREFILL_SYSTEM = (
    "你是工时填报助手。根据任务的近期进度记录与填报人近期工时，给出当日工时建议，输出严格 JSON："
    '{"hours":数字（0.5-24，0.5 步进）,"content":"当日工作内容草稿（客观描述完成事项，200字内）"}。'
    "参考当日已报工时合计，避免全天合计明显超过 24 小时；只输出 JSON，不要输出其他内容。"
)

_PROGRESS_LIMIT = 5
_RECENT_LIMIT = 5


def _round_half(v: float) -> float:
    """0.5 步进取整（就近），clamp 到 [0.5, 24]。"""
    stepped = round(v * 2) / 2
    return max(0.5, min(stepped, 24.0))


def parse_prefill_output(raw: str) -> dict:
    """AI 输出 → {hours, content}。无法解析/缺字段抛 BizException(AI_PARSE_FAILED)。"""
    try:
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
        hours = float(parsed.get("hours"))
    except (ValueError, TypeError) as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 输出无法解析，请稍后再试") from exc
    content = str(parsed.get("content") or "").strip()[:500]
    if not content:
        raise BizException(R.AI_PARSE_FAILED, "AI 未给出工作内容草稿，请稍后再试")
    return {"hours": _round_half(hours), "content": content}


def build_prefill_context(db: Session, user: User, task_id: int, work_date: date) -> dict:
    """组装 prompt 上下文：任务信息 + 最近进度日志 + 本人该任务近期工时 + 当日已报合计。"""
    task = _fillable_task(db, task_id)
    progress = list(
        db.scalars(
            select(TaskProgressLog)
            .where(TaskProgressLog.task_id == task_id, TaskProgressLog.deleted == 0)
            .order_by(TaskProgressLog.id.desc())
            .limit(_PROGRESS_LIMIT)
        ).all()
    )
    recent = list(
        db.scalars(
            select(HrTimesheet)
            .where(
                HrTimesheet.user_id == user.id,
                HrTimesheet.task_id == task_id,
                HrTimesheet.deleted == 0,
                HrTimesheet.work_date < work_date,
            )
            .order_by(HrTimesheet.work_date.desc())
            .limit(_RECENT_LIMIT)
        ).all()
    )
    day_used = db.scalar(
        select(func.coalesce(func.sum(HrTimesheet.hours), 0)).where(
            HrTimesheet.user_id == user.id,
            HrTimesheet.work_date == work_date,
            HrTimesheet.deleted == 0,
        )
    )
    return {
        "task": {"taskNo": task.task_no or "", "taskName": task.task_name, "customerName": task.customer_name},
        "workDate": work_date.isoformat(),
        "dayUsedHours": float(day_used or 0),
        "progressLogs": [
            {
                "time": p.create_time.strftime("%Y-%m-%d %H:%M") if p.create_time else "",
                "percent": p.percent,
                "note": (p.note or "")[:200],
            }
            for p in progress
        ],
        "recentTimesheets": [
            {"workDate": t.work_date.isoformat(), "hours": float(t.hours), "content": (t.content or "")[:200]}
            for t in recent
        ],
    }


def ai_prefill(db: Session, user: User, task_id: int, work_date: date) -> dict:
    """工时预填入口：任务须可填报（进行中且挂合同）；只回草稿不落库。"""
    from app.services import ai as ai_svc

    _check_date(work_date)
    if not ai_svc.ai_ready(db):
        raise BizException(R.AI_NOT_CONFIGURED, "AI 未配置或工时预填功能已停用")

    ctx = build_prefill_context(db, user, task_id, work_date)
    basis = {
        "progressCount": len(ctx["progressLogs"]),
        "recentCount": len(ctx["recentTimesheets"]),
        "dayUsedHours": ctx["dayUsedHours"],
    }
    messages = [
        {"role": "system", "content": PREFILL_SYSTEM},
        {"role": "user", "content": json.dumps(ctx, ensure_ascii=False)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db,
            feature="hr_prefill",
            messages=messages,
            user=user,
            biz_type="hr_timesheet",
            biz_id=task_id,
            prompt_version=PREFILL_PROMPT_VERSION,
        )
    except ai_svc.AiUnavailable as exc:
        raise BizException(R.AI_PARSE_FAILED, "AI 服务调用失败，请稍后重试") from exc
    result = parse_prefill_output(raw)
    result["basis"] = basis
    return result
