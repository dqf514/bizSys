"""AI 每日待办摘要：聚合当前用户待审批/进行中任务/临期逾期 → 一段话摘要；可推送企微（未配置走站内通知）。"""

import json
import logging
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.admin.models import Notify
from app.modules.approval.models import ApprovalInstance, ApprovalTask
from app.modules.auth.models import User
from app.modules.task.models import Task
from app.services import ai as ai_svc
from app.services import prompts

logger = logging.getLogger("bizsys.ai.digest")

DUE_SOON_DAYS = 3


def collect_todos(db: Session, user: User) -> dict:
    """今日待办原始数据（确定性查询，不经 AI）。"""
    today = date.today()
    approval_rows = db.execute(
        select(ApprovalTask, ApprovalInstance.title)
        .join(ApprovalInstance, ApprovalInstance.id == ApprovalTask.instance_id)
        .where(
            ApprovalTask.deleted == 0,
            ApprovalTask.assignee_id == user.id,
            ApprovalTask.status == "pending",
            ApprovalInstance.status == "running",
        )
        .order_by(ApprovalTask.id.desc())
        .limit(5)
    ).all()
    approvals = [{"title": title, "node": t.node_name} for t, title in approval_rows]
    approval_count = db.scalar(
        select(func.count(ApprovalTask.id))
        .join(ApprovalInstance, ApprovalInstance.id == ApprovalTask.instance_id)
        .where(
            ApprovalTask.deleted == 0,
            ApprovalTask.assignee_id == user.id,
            ApprovalTask.status == "pending",
            ApprovalInstance.status == "running",
        )
    ) or 0

    task_rows = list(
        db.scalars(
            select(Task).where(
                Task.deleted == 0,
                Task.owner_id == user.id,
                Task.status == "in_progress",
                Task.plan_finish_date.is_not(None),
                Task.plan_finish_date <= today + timedelta(days=DUE_SOON_DAYS),
            )
            .order_by(Task.plan_finish_date)
            .limit(10)
        ).all()
    )
    overdue = [
        {"title": t.task_name, "dueDate": str(t.plan_finish_date)}
        for t in task_rows
        if t.plan_finish_date < today
    ]
    due_soon = [
        {"title": t.task_name, "dueDate": str(t.plan_finish_date)}
        for t in task_rows
        if t.plan_finish_date >= today
    ]
    return {
        "date": today.isoformat(),
        "approvalCount": approval_count,
        "approvals": approvals,
        "overdueTasks": overdue,
        "dueSoonTasks": due_soon,
    }


def _fallback_summary(todos: dict) -> dict:
    """无 AI 时的模板化摘要（降级可用）。"""
    parts = [f"今日有 {todos['approvalCount']} 项审批待办"]
    if todos["overdueTasks"]:
        parts.append(f"{len(todos['overdueTasks'])} 项任务已逾期")
    if todos["dueSoonTasks"]:
        parts.append(f"{len(todos['dueSoonTasks'])} 项任务临近截止")
    highlights = [f"逾期：{t['title']}" for t in todos["overdueTasks"][:3]]
    highlights += [f"待审批：{a['title']}" for a in todos["approvals"][: max(0, 3 - len(highlights))]]
    return {"summary": "；".join(parts) + "。", "highlights": highlights[:3], "degraded": True}


def daily_digest(db: Session, user: User) -> dict:
    """聚合待办 → AI 一段话摘要。AI 不可用/功能关闭时回退模板摘要。"""
    todos = collect_todos(db, user)
    if not ai_svc.feature_enabled(db, "daily_digest"):
        return {**_fallback_summary(todos), "todos": todos}
    messages = [
        {"role": "system", "content": prompts.get("daily_digest")["system"]},
        {"role": "user", "content": json.dumps(todos, ensure_ascii=False)},
    ]
    try:
        raw = ai_svc.gateway_chat(
            db, feature="daily_digest", messages=messages, user=user,
            biz_type="daily_digest", prompt_version=prompts.feature_version("daily_digest"),
            json_mode=True, max_tokens=500,
        )
        parsed = json.loads(raw.strip().removeprefix("```json").removesuffix("```").strip())
        summary = str(parsed.get("summary") or "").strip()
        highlights = [str(h)[:200] for h in (parsed.get("highlights") or [])[:3]]
        if not summary:
            raise ValueError("empty summary")
    except (ai_svc.AiUnavailable, ValueError, TypeError):
        return {**_fallback_summary(todos), "todos": todos}
    return {"summary": summary[:1000], "highlights": highlights, "degraded": False, "todos": todos}


def push_digest(db: Session, user: User, summary: str, highlights: list[str]) -> dict:
    """推送摘要给本人：企微凭据就绪且已绑定 → 企微；否则站内通知。通道失败不阻断。"""
    from app.modules.integration.adapters import ADAPTERS
    from app.modules.settings import service as settings_svc

    content = summary + ("\n" + "\n".join(f"· {h}" for h in highlights) if highlights else "")
    channel = "notify"
    if user.wecom_userid and settings_svc.wecom_ready(db):
        _, corp_id, agent_id, secret = settings_svc.wecom_creds(db)
        try:
            ADAPTERS["wecom"].send_message(
                user.wecom_userid, "AI 每日待办摘要",
                corp_id=corp_id, secret=secret, agent_id=agent_id,
                description=summary[:120],
            )
            channel = "wecom"
        except Exception as exc:  # noqa: BLE001 —— 外部通道失败回落站内
            logger.warning("wecom digest push failed: user=%s err=%s", user.id, exc)
    db.add(
        Notify(
            user_id=user.id,
            title="AI 每日待办摘要",
            content=content[:2000],
            biz_type="daily_digest",
            link="/workbench",
            create_by=user.id,
        )
    )
    db.flush()
    return {"channel": channel}
