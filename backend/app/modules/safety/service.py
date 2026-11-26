"""安全巡检域（B8 / CSV 24）业务规则。

职责边界：
- **状态机与副作用**（提交记录自动生成隐患、整改 / 验证闭环、巡检闭环校验）在本模块；
- **列表检索 / 序列化 / 审计 / commit** 在 `router.py`。
"""

import json
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.safety.models import SafetyHazard, SafetyInspection, SafetyInspectionPlan
from app.services.numbering import next_no

# ---------------- 枚举 ----------------

PLAN_TYPES = ("daily", "weekly", "monthly", "special")
PLAN_STATUSES = ("active", "paused", "finished")
INSPECTION_STATUSES = ("draft", "submitted", "closed")
INSPECTION_RESULTS = ("normal", "abnormal")
HAZARD_LEVELS = ("low", "medium", "high", "critical")
HAZARD_STATUSES = ("open", "rectifying", "verified", "closed")
HAZARD_SOURCES = ("inspection", "manual")

PLAN_TYPE_CN = {
    "daily": "每日",
    "weekly": "每周",
    "monthly": "每月",
    "special": "专项",
}
PLAN_STATUS_CN = {"active": "执行中", "paused": "暂停", "finished": "已结束"}
INSPECTION_STATUS_CN = {"draft": "草稿", "submitted": "已提交", "closed": "已闭环"}
INSPECTION_RESULT_CN = {"normal": "正常", "abnormal": "异常"}
HAZARD_LEVEL_CN = {"low": "一般", "medium": "较大", "high": "重大", "critical": "紧急"}
HAZARD_STATUS_CN = {"open": "待整改", "rectifying": "整改中", "verified": "待验证", "closed": "已关闭"}
HAZARD_SOURCE_CN = {"inspection": "巡检发现", "manual": "手工上报"}

# 新发现隐患的默认整改期限（天）
DEFAULT_HAZARD_DEADLINE_DAYS = 7
# 巡检完成率统计窗口（天）
COMPLETION_WINDOW_DAYS = 30
# 月度趋势统计窗口（月）
TREND_MONTHS = 6


# ---------------- 工具 ----------------


def _json_load(raw: str | None) -> Any:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


def parse_items(raw: str | None) -> list[dict]:
    """解析逐项结果；非法结构一律降级为空数组（不抛错，坏数据不应阻断列表）。"""
    data = _json_load(raw)
    if not isinstance(data, list):
        return []
    items: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        items.append(
            {
                "item": str(row.get("item") or ""),
                "result": str(row.get("result") or "normal"),
                "note": str(row.get("note") or ""),
            }
        )
    return items


def dump_items(items: list[dict]) -> str:
    return json.dumps(items, ensure_ascii=False, default=str)


def plan_items(plan: SafetyInspectionPlan | None) -> list[str]:
    """计划里的巡检项清单。"""
    if plan is None:
        return []
    data = _json_load(plan.check_items)
    if isinstance(data, list):
        return [str(x) for x in data if str(x).strip()]
    return []


def abnormal_items(raw: str | None) -> list[dict]:
    return [it for it in parse_items(raw) if it.get("result") == "abnormal"]


def ensure_no_available(db: Session, model, field: str, value: str, label: str) -> None:
    """编号唯一性校验（软删的单据也不允许复用编号，避免回收站恢复时撞唯一键）。"""
    if not value:
        return
    existing = db.scalar(select(model).where(getattr(model, field) == value))
    if existing is None:
        return
    if getattr(existing, "deleted", 0):
        raise BizException(R.SAFETY_INVALID_STATE, f"{label}已存在（已删除的单据编号不可复用）：{value}")
    raise BizException(R.SAFETY_INVALID_STATE, f"{label}已存在：{value}")


def is_overdue(hazard: SafetyHazard, today: date | None = None) -> bool:
    """逾期 = 已过整改期限且尚未关闭。"""
    if hazard.status == "closed":
        return False
    if hazard.deadline is None:
        return False
    return hazard.deadline < (today or date.today())


def next_plan_no(db: Session) -> str:
    """计划编号：优先取号规则（`safety_plan`），缺失时用日期流水兜底。"""
    try:
        return next_no(db, "safety_plan")
    except BizException:
        prefix = f"JH{date.today():%Y%m%d}"
        n = db.scalar(
            select(func.count()).select_from(SafetyInspectionPlan).where(
                SafetyInspectionPlan.plan_no.like(f"{prefix}%")
            )
        ) or 0
        return f"{prefix}{n + 1:04d}"


def next_record_no(db: Session) -> str:
    """记录编号：优先取号规则（`safety_inspection`），缺失时用日期流水兜底。"""
    try:
        return next_no(db, "safety_inspection")
    except BizException:
        prefix = f"XJ{date.today():%Y%m%d}"
        n = db.scalar(
            select(func.count()).select_from(SafetyInspection).where(
                SafetyInspection.record_no.like(f"{prefix}%")
            )
        ) or 0
        return f"{prefix}{n + 1:04d}"


def next_hazard_no(db: Session) -> str:
    """隐患编号：优先取号规则（`safety_hazard`），缺失时用日期流水兜底。"""
    try:
        return next_no(db, "safety_hazard")
    except BizException:
        prefix = f"YH{date.today():%Y%m%d}"
        n = db.scalar(
            select(func.count()).select_from(SafetyHazard).where(SafetyHazard.hazard_no.like(f"{prefix}%"))
        ) or 0
        return f"{prefix}{n + 1:04d}"


# ---------------- 巡检记录 ----------------


def recalc_result(rec: SafetyInspection) -> str:
    """按逐项结果重算总结果与异常项数（异常项以逐项为准，缺逐项时保留原值）。"""
    items = parse_items(rec.items_json)
    if not items:
        return rec.result
    abnormal = [it for it in items if it.get("result") == "abnormal"]
    rec.abnormal_count = len(abnormal)
    rec.result = "abnormal" if abnormal else "normal"
    return rec.result


def submit_inspection(db: Session, rec: SafetyInspection, user) -> list[int]:
    """提交巡检记录：异常项自动生成隐患（待整改），状态置「已提交」。"""
    if rec.status != "draft":
        raise BizException(R.SAFETY_INVALID_STATE, "巡检记录已提交，不能重复提交")
    items = parse_items(rec.items_json)
    recalc_result(rec)
    now = datetime.now()
    hazard_ids: list[int] = []
    for it in items:
        if it.get("result") != "abnormal":
            continue
        hazard = SafetyHazard(
            hazard_no=next_hazard_no(db),
            inspection_id=rec.id,
            record_no=rec.record_no,
            source="inspection",
            description=it.get("note") or it.get("item") or "",
            level="medium",
            status="open",
            deadline=(now + timedelta(days=DEFAULT_HAZARD_DEADLINE_DAYS)).date(),
            found_at=now,
            remark=it.get("item") or "",
        )
        db.add(hazard)
        db.flush()
        hazard_ids.append(hazard.id)
    rec.status = "submitted"
    return hazard_ids


def close_inspection(db: Session, rec: SafetyInspection) -> None:
    """巡检记录闭环：关联隐患必须全部关闭。"""
    if rec.status == "draft":
        raise BizException(R.SAFETY_INVALID_STATE, "草稿状态的巡检记录不能闭环")
    if rec.status == "closed":
        raise BizException(R.SAFETY_INVALID_STATE, "巡检记录已闭环")
    pending = db.scalars(
        select(SafetyHazard).where(
            SafetyHazard.inspection_id == rec.id,
            SafetyHazard.deleted == 0,
            SafetyHazard.status != "closed",
        )
    ).all()
    if pending:
        raise BizException(
            R.SAFETY_INVALID_STATE,
            f"仍有 {len(pending)} 条隐患未关闭，不能闭环",
        )
    rec.status = "closed"


# ---------------- 隐患 ----------------


def rectify_hazard(db: Session, hazard: SafetyHazard, measure: str, user) -> None:
    """隐患整改：登记整改措施 → 待验证。"""
    if hazard.status == "closed":
        raise BizException(R.SAFETY_INVALID_STATE, "隐患已关闭，不能再整改")
    if not (measure or "").strip():
        raise BizException(R.SAFETY_INVALID_STATE, "整改措施必填")
    hazard.measure = measure.strip()
    hazard.rectified_at = datetime.now()
    hazard.rectified_by_name = (user.name or user.username) if user is not None else ""
    # 「待整改」首次整改 → 整改中；再次整改（整改中）→ 待验证，交由验证人确认闭环
    hazard.status = "rectifying" if hazard.status == "open" else "verified"


def verify_hazard(db: Session, hazard: SafetyHazard, verify_result: str, passed: bool, user) -> None:
    """隐患验证：通过 → 已关闭；不通过 → 退回整改中。"""
    if hazard.status == "closed":
        raise BizException(R.SAFETY_INVALID_STATE, "隐患已关闭，不能重复验证")
    now = datetime.now()
    hazard.verify_result = (verify_result or "").strip()
    hazard.verify_by_name = (user.name or user.username) if user is not None else ""
    hazard.verified_at = now
    hazard.status = "closed" if passed else "rectifying"


# ---------------- 看板 ----------------


def board(db: Session) -> dict:
    """统计看板：等级 / 状态 / 区域分布、逾期 Top、巡检完成率、月度隐患趋势。"""
    now = datetime.now()
    today = now.date()

    plan_total = db.scalar(
        select(func.count()).select_from(SafetyInspectionPlan).where(SafetyInspectionPlan.deleted == 0)
    ) or 0
    plan_active = db.scalar(
        select(func.count())
        .select_from(SafetyInspectionPlan)
        .where(SafetyInspectionPlan.deleted == 0, SafetyInspectionPlan.status == "active")
    ) or 0

    month_start = today.replace(day=1)
    month_inspections = db.scalar(
        select(func.count())
        .select_from(SafetyInspection)
        .where(
            SafetyInspection.deleted == 0,
            SafetyInspection.inspect_date >= month_start,
        )
    ) or 0

    hazards = db.scalars(select(SafetyHazard).where(SafetyHazard.deleted == 0)).all()
    open_hazards = [h for h in hazards if h.status != "closed"]
    overdue = [h for h in hazards if is_overdue(h, today)]

    by_level: dict[str, int] = {lv: 0 for lv in HAZARD_LEVELS}
    by_status: dict[str, int] = {st: 0 for st in HAZARD_STATUSES}
    for h in hazards:
        by_level[h.level] = by_level.get(h.level, 0) + 1
        by_status[h.status] = by_status.get(h.status, 0) + 1

    # 区域分布：隐患跟随来源巡检记录的区域；手工上报归到 manual
    area_map: dict[str, str] = {}
    if hazards:
        insp_ids = {h.inspection_id for h in hazards if h.inspection_id}
        if insp_ids:
            for row in db.execute(
                select(SafetyInspection.id, SafetyInspection.area).where(SafetyInspection.id.in_(insp_ids))
            ).all():
                area_map[row[0]] = row[1] or ""
    by_area: dict[str, int] = {}
    for h in hazards:
        area = area_map.get(h.inspection_id, "") if h.inspection_id else ""
        key = area or "manual"
        by_area[key] = by_area.get(key, 0) + 1

    overdue_top = sorted(overdue, key=lambda h: (h.deadline or today, h.id))[:10]
    overdue_rows = [
        {
            "id": h.id,
            "hazardNo": h.hazard_no,
            "description": h.description,
            "level": h.level,
            "deadline": h.deadline.strftime("%Y-%m-%d") if h.deadline else "",
            "responsibleName": h.responsible_name,
            "daysOverdue": (today - h.deadline).days if h.deadline else 0,
        }
        for h in overdue_top
    ]

    # 巡检完成率：近 30 天已提交 / 已闭环记录数 ÷ 执行中的计划数
    since = today - timedelta(days=COMPLETION_WINDOW_DAYS)
    done = db.scalar(
        select(func.count())
        .select_from(SafetyInspection)
        .where(
            SafetyInspection.deleted == 0,
            SafetyInspection.status.in_(("submitted", "closed")),
            SafetyInspection.inspect_date >= since,
        )
    ) or 0
    rate = round(done / plan_active * 100, 1) if plan_active else 0.0

    # 月度隐患趋势（近 6 个月，含当月）
    month_label = func.date_format(SafetyHazard.found_at, "%Y-%m").label("m")
    trend_rows = db.execute(
        select(month_label, func.count())
        .where(SafetyHazard.deleted == 0)
        .group_by(month_label)
        .order_by(month_label)
    ).all()
    trend_map = {str(r[0]): int(r[1]) for r in trend_rows}
    trend: list[dict] = []
    cursor = month_start
    for _ in range(TREND_MONTHS):
        key = f"{cursor.year:04d}-{cursor.month:02d}"
        trend.append({"month": key, "count": trend_map.get(key, 0)})
        cursor = (cursor - timedelta(days=1)).replace(day=1)

    return {
        "planTotal": plan_total,
        "planActive": plan_active,
        "monthInspections": month_inspections,
        "openHazards": len(open_hazards),
        "overdueHazards": len(overdue),
        "byLevel": [{"level": k, "count": v} for k, v in by_level.items()],
        "byStatus": [{"status": k, "count": v} for k, v in by_status.items()],
        "byArea": [{"area": k, "count": v} for k, v in sorted(by_area.items(), key=lambda kv: -kv[1])],
        "overdueTop": overdue_rows,
        "completion": {"planCount": plan_active, "doneCount": done, "rate": rate},
        "monthlyTrend": trend,
    }
