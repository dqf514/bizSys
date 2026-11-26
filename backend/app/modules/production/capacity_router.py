"""产能利用率看板（B7 CSV 4）。

看板内容：风洞台次利用率、风洞中心设备利用率、加工中心设备利用率，
并与设备台账（`ast_equipment`，B4/B6 批次）联动。

============================ 利用率口径（企业最佳实践） ============================

1. **排程占用工时** = `prd_schedule` 中 `resource_type='equipment'` 且
   `status ∈ {scheduled, published, confirmed, done}` 的 `duration_hours` 求和。
   - `status='conflict'` 的行**单独计入冲突数，不占用工时**（冲突排程尚未真正占用资源）。
   - `status='cancelled'` 的行不计入任何口径。
   - 统计范围：**计划开始时间**落在 `[from 00:00:00, to 23:59:59]` 内的行。

2. **可用工时** = 期间天数 × 24 小时 × 设备可用系数
   - 系数 1.0：idle / running（正常可用）
   - 系数 0.5：maintenance / fault（维护与故障期间只按一半算力折算）
   - 系数 0.0：scrapped（已报废，不计可用工时，利用率按 0 处理）

3. **利用率** = 排程占用工时 ÷ 可用工时 × 100%，**允许 > 100%**（表示超负荷 / 存在冲突），
   > 100% 的设备计入「超负荷设备数」。

4. **平均利用率** = 期间内所有「可用工时 > 0」的设备的利用率算术平均（含零排程的闲置设备）。

5. **台次利用率**：风洞等按「台次」计量的业务，用**排程行数**（scheduleCount）表达；
   分类维度的 `scheduleCount` 即该分类期间内的风洞台次数。

6. **无设备台账数据时**（`ast_equipment` 尚未落地）：只按排程行的
   `resource_id` / `resource_name` 聚合，`equipmentId` 为 null，可用工时按 24h/天计。

7. **设备名称 / 状态**优先取 `ast_equipment`；取不到则回退到排程行的 `resource_name`。
   排程行与台账的关联优先级为 **编号（resource_code = equipment_no） > 名称（resource_name = name） > id**；
   排程行给了编号但台账查不到时按「未登记设备」处理（不按 id 猜），避免误配。

8. **趋势分桶**：区间 ≤ 31 天按日，否则按自然周（key 用该周周一日期）。

**降级策略**：`ast_equipment` 由并行批次创建，可能尚不存在 —— 这里延迟导入模型，
导入失败或查询失败（表未建）时按「无设备台账数据」降级，整个接口不会 500。
==============================================================================
"""

from __future__ import annotations

import importlib
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.production.models import ProdSchedule

capacity_router = APIRouter(prefix="/production", tags=["production"], route_class=EnvelopeRoute)

# 设备台账表名（B4/B6 批次创建，可能尚不存在 → 延迟导入 + 失败降级）
EQUIPMENT_TABLE = "ast_equipment"

# 设备不存在 / 不在统计范围内。
# 注意：本常量**尚未登记进 app/core/response.py**（需与前端 src/api/types.ts 双侧登记）。
PRODUCTION_CAPACITY_NOT_FOUND = 99006

# 占用设备时段的排程行状态；冲突行单独统计且不占用工时
OCCUPY_STATUS = ("scheduled", "published", "confirmed", "done")
CONFLICT_STATUS = "conflict"

DEFAULT_PERIOD_DAYS = 30
MAX_EQUIPMENT_ROWS = 100
MAX_CONFLICT_ROWS = 200

CATEGORY_CN = {
    "wind_tunnel": "风洞",
    "cfd": "CFD",
    "machining": "加工",
    "test": "试验",
    "other": "其他",
}

EQUIPMENT_STATUS_CN = {
    "idle": "闲置",
    "running": "运行中",
    "maintenance": "维护中",
    "fault": "故障",
    "scrapped": "已报废",
}

SCHEDULE_STATUS_CN = {
    "scheduled": "已排期",
    "published": "已发布",
    "confirmed": "已确认",
    "done": "已完成",
    "conflict": "冲突",
    "cancelled": "已取消",
}

# 未登记设备的分类推断关键词（台账缺失时的启发式兜底）
CATEGORY_KEYWORDS = (
    ("wind_tunnel", ("风洞", "wind tunnel", "windtunnel")),
    ("cfd", ("cfd", "流体", "数值模拟")),
    ("machining", ("加工", "机床", "数控", "machining")),
    ("test", ("试验", "测试")),
)


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _d(v) -> str:
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _text(mapping: dict[str, str], value: str | None) -> str:
    key = value or ""
    return mapping.get(key, key)


def _round(v: float, digits: int = 2) -> float:
    return round(float(v) + 0.0, digits)


# ---------------- 设备台账（可选数据源，缺失时降级） ----------------


def _equipment_model():
    """定位设备台账模型（按表名匹配，避免依赖类名与所在模块）。

    设备台账由 B6 批次创建（`app.modules.asset.equipment_models.Equipment`），
    但类名 / 所在模块仍可能变动 —— 这里扫描若干候选模块中表名为
    `ast_equipment` 的映射类。找不到（或表还没建）返回 None，走「无台账数据」降级分支。
    """
    for module_path in (
        "app.modules.asset.equipment_models",
        "app.modules.asset.models",
    ):
        try:
            module = importlib.import_module(module_path)
        except Exception:  # pragma: no cover - 候选模块尚未就绪
            continue
        for obj in list(vars(module).values()):
            if getattr(obj, "__tablename__", None) == EQUIPMENT_TABLE:
                return obj
    return None


def _load_equipment_rows(db: Session) -> dict[int, Any]:
    """读取设备台账：{id: 设备行}。表未建 / 查询失败时返回空字典（不抛错）。

    用 SAVEPOINT 包裹查询：MySQL 报表不存在（1146）时回滚到保存点，
    避免把整个请求事务置为失败态。
    """
    model = _equipment_model()
    if model is None:
        return {}
    deleted_col = getattr(model, "deleted", None)
    try:
        with db.begin_nested():
            stmt = select(model)
            if deleted_col is not None:
                stmt = stmt.where(deleted_col == 0)
            rows = db.scalars(stmt).all()
            return {r.id: r for r in rows}
    except Exception:
        return {}


def _availability_factor(status: str) -> float:
    """设备可用系数：维护 / 故障按 50%，报废不计。"""
    if status in ("maintenance", "fault"):
        return 0.5
    if status == "scrapped":
        return 0.0
    return 1.0


def _infer_category(name: str) -> str:
    """未登记设备的分类推断（仅在设备台账缺失时使用）。

    台账一旦落地就以台账的 `category` 为准；这里的关键词推断只是为了让
    「风洞台次利用率 / 加工中心设备利用率」在台账上线前也有意义，
    属于**启发式兜底**，不是权威口径。
    """
    low = (name or "").lower()
    for cat, keywords in CATEGORY_KEYWORDS:
        if any(k in low for k in keywords):
            return cat
    return "other"


def _new_entry(
    equipment_id: int | None,
    equipment_no: str,
    equipment_name: str,
    category: str,
    workshop: str,
    status: str,
    run_hours: float,
) -> dict:
    return {
        "equipmentId": equipment_id,
        "equipmentNo": equipment_no or "",
        "equipmentName": equipment_name or "",
        "category": category or "other",
        "workshop": workshop or "",
        "status": status or "idle",
        "runHours": run_hours,
        "scheduleHours": 0.0,
        "scheduleCount": 0,
        "conflictCount": 0,
        "tasks": set(),
        "lastEnd": None,
        "factor": _availability_factor(status or "idle"),
    }


def _hours(row: ProdSchedule) -> float:
    """排程行占用工时：优先取 duration_hours，缺失时按起止时间推算。"""
    h = _f(row.duration_hours)
    if h <= 0 and row.plan_start and row.plan_end:
        h = (row.plan_end - row.plan_start).total_seconds() / 3600
    return max(h, 0.0)


def _match_entry(
    row: ProdSchedule,
    ledger: dict[int, Any],
    by_no: dict[str, dict],
    by_name: dict[str, dict],
    pseudo: dict[tuple, dict],
) -> dict:
    """把一条排程行定位到设备条目；台账里找不到时按排程行自身建「未登记设备」条目。

    匹配优先级（**编号 > 名称 > id**）：排程行的 `resource_id` 没有到台账的外键约束，
    直接按 id 关联可能误配，所以只有在排程行**没有给出编号**时才用 id 兜底；
    给了编号但台账里查不到，说明该编号未登记 —— 按「未登记设备」处理（不猜 id）。
    """
    code = (row.resource_code or "").strip()
    name = (row.resource_name or "").strip()
    if code and code in by_no:
        return by_no[code]
    if name and name in by_name:
        return by_name[name]
    if not code and row.resource_id is not None and row.resource_id in ledger:
        return ledger[row.resource_id]
    key = ("id", row.resource_id) if row.resource_id is not None else ("name", name)
    entry = pseudo.get(key)
    if entry is None:
        entry = _new_entry(None, code, name, _infer_category(name), "", "idle", 0.0)
        pseudo[key] = entry
    return entry


def _entry_out(entry: dict, days: int) -> dict:
    available = days * 24 * entry["factor"]
    schedule_hours = entry["scheduleHours"]
    utilization = _round(schedule_hours / available * 100) if available > 0 else 0.0
    return {
        "equipmentId": entry["equipmentId"],
        "equipmentNo": entry["equipmentNo"],
        "equipmentName": entry["equipmentName"],
        "category": entry["category"],
        "categoryText": _text(CATEGORY_CN, entry["category"]),
        "workshop": entry["workshop"],
        "status": entry["status"],
        "statusText": _text(EQUIPMENT_STATUS_CN, entry["status"]),
        "scheduleHours": _round(schedule_hours),
        "availableHours": _round(available),
        "utilization": utilization,
        "scheduleCount": entry["scheduleCount"],
        "conflictCount": entry["conflictCount"],
        "taskCount": len(entry["tasks"]),
        "runHours": _round(entry["runHours"]),
        "lastScheduleEnd": _t(entry["lastEnd"]),
        "overloaded": utilization > 100,
    }


def _bucket_plan(d1: date, d2: date, by_week: bool) -> list[tuple[date, date, date]]:
    """趋势分桶：(桶 key, 桶内有效起日, 桶内有效止日)。按日或按自然周（周一为 key）。"""
    out: list[tuple[date, date, date]] = []
    cur = d1
    while cur <= d2:
        if by_week:
            start = cur - timedelta(days=cur.weekday())
            end = start + timedelta(days=6)
        else:
            start = end = cur
        eff_start = max(start, d1)
        eff_end = min(end, d2)
        out.append((start, eff_start, eff_end))
        cur = end + timedelta(days=1)
    return out


def _build_board(
    db: Session,
    date_from: date,
    date_to: date,
    workshop: str | None,
    category: str | None,
) -> dict:
    days = (date_to - date_from).days + 1
    if days <= 0:
        days = 1
    start_dt = datetime.combine(date_from, datetime.min.time())
    end_dt = datetime.combine(date_to, datetime.max.time())

    rows = list(
        db.scalars(
            select(ProdSchedule).where(
                ProdSchedule.deleted == 0,
                ProdSchedule.resource_type == "equipment",
                ProdSchedule.status.in_(OCCUPY_STATUS + (CONFLICT_STATUS,)),
                ProdSchedule.plan_start >= start_dt,
                ProdSchedule.plan_start <= end_dt,
            )
        ).all()
    )

    ledger = _load_equipment_rows(db)
    entries: list[dict] = []
    ledger_by_id: dict[int, dict] = {}
    by_no: dict[str, dict] = {}
    by_name: dict[str, dict] = {}
    for eq in ledger.values():
        entry = _new_entry(
            eq.id,
            getattr(eq, "equipment_no", "") or "",
            getattr(eq, "name", "") or "",
            getattr(eq, "category", "other") or "other",
            getattr(eq, "workshop", "") or "",
            getattr(eq, "status", "idle") or "idle",
            _f(getattr(eq, "run_hours", 0)),
        )
        entries.append(entry)
        ledger_by_id[eq.id] = entry
        if entry["equipmentNo"]:
            by_no.setdefault(entry["equipmentNo"], entry)
        if entry["equipmentName"]:
            by_name.setdefault(entry["equipmentName"], entry)

    pseudo: dict[tuple, dict] = {}
    conflict_rows: list[tuple[ProdSchedule, dict]] = []
    for row in rows:
        entry = _match_entry(row, ledger_by_id, by_no, by_name, pseudo)
        if row.status == CONFLICT_STATUS:
            entry["conflictCount"] += 1
            conflict_rows.append((row, entry))
            continue
        entry["scheduleHours"] += _hours(row)
        entry["scheduleCount"] += 1
        if row.task_id:
            entry["tasks"].add(("id", row.task_id))
        elif row.task_no:
            entry["tasks"].add(("no", row.task_no))
        if row.plan_end and (entry["lastEnd"] is None or row.plan_end > entry["lastEnd"]):
            entry["lastEnd"] = row.plan_end

    entries.extend(pseudo.values())

    # 车间 / 分类过滤
    ws = (workshop or "").strip()
    cat = (category or "").strip()
    if ws:
        entries = [e for e in entries if e["workshop"] == ws]
    if cat:
        entries = [e for e in entries if e["category"] == cat]

    outs = [_entry_out(e, days) for e in entries]

    # ---------------- 汇总 ----------------
    total_hours = sum(o["scheduleHours"] for o in outs)
    valid = [o for o in outs if o["availableHours"] > 0]
    avg_util = _round(sum(o["utilization"] for o in valid) / len(valid)) if valid else 0.0
    summary = {
        "equipmentTotal": len(outs),
        "scheduledEquipment": sum(1 for o in outs if o["scheduleCount"] > 0),
        "avgUtilization": avg_util,
        "totalScheduleHours": _round(total_hours),
        "conflictCount": sum(o["conflictCount"] for o in outs),
        "idleEquipment": sum(1 for o in outs if o["scheduleCount"] == 0),
        "overloadEquipment": sum(1 for o in outs if o["utilization"] > 100),
        "periodCount": days,
    }

    # ---------------- 分类维度（含风洞台次） ----------------
    by_category: dict[str, dict] = {}
    for o in outs:
        bucket = by_category.setdefault(
            o["category"],
            {
                "category": o["category"],
                "categoryText": o["categoryText"],
                "equipmentCount": 0,
                "scheduleHours": 0.0,
                "availableHours": 0.0,
                "utilization": 0.0,
                "scheduleCount": 0,
            },
        )
        bucket["equipmentCount"] += 1
        bucket["scheduleHours"] += o["scheduleHours"]
        bucket["availableHours"] += o["availableHours"]
        bucket["scheduleCount"] += o["scheduleCount"]
    for bucket in by_category.values():
        bucket["scheduleHours"] = _round(bucket["scheduleHours"])
        bucket["availableHours"] = _round(bucket["availableHours"])
        bucket["utilization"] = (
            _round(bucket["scheduleHours"] / bucket["availableHours"] * 100)
            if bucket["availableHours"] > 0
            else 0.0
        )
    category_list = sorted(by_category.values(), key=lambda b: b["utilization"], reverse=True)

    # ---------------- 车间维度 ----------------
    by_workshop: dict[str, dict] = {}
    for o in outs:
        bucket = by_workshop.setdefault(
            o["workshop"],
            {
                "workshop": o["workshop"],
                "equipmentCount": 0,
                "scheduleHours": 0.0,
                "availableHours": 0.0,
                "utilization": 0.0,
            },
        )
        bucket["equipmentCount"] += 1
        bucket["scheduleHours"] += o["scheduleHours"]
        bucket["availableHours"] += o["availableHours"]
    for bucket in by_workshop.values():
        bucket["scheduleHours"] = _round(bucket["scheduleHours"])
        bucket["availableHours"] = _round(bucket["availableHours"])
        bucket["utilization"] = (
            _round(bucket["scheduleHours"] / bucket["availableHours"] * 100)
            if bucket["availableHours"] > 0
            else 0.0
        )
    workshop_list = sorted(by_workshop.values(), key=lambda b: b["utilization"], reverse=True)

    # ---------------- 趋势 ----------------
    by_week = days > 31
    daily_factor = sum(e["factor"] for e in entries)
    buckets = _bucket_plan(date_from, date_to, by_week)
    trend_map: dict[str, dict] = {}
    for key, eff_start, eff_end in buckets:
        span = (eff_end - eff_start).days + 1
        trend_map[key.isoformat()] = {
            "bucket": key.isoformat(),
            "scheduleHours": 0.0,
            "availableHours": _round(span * 24 * daily_factor),
            "utilization": 0.0,
            "scheduleCount": 0,
            "conflictCount": 0,
        }
    for row in rows:
        if not row.plan_start:
            continue
        row_date = row.plan_start.date()
        key = row_date.isoformat()
        if not by_week:
            bucket_key = key
        else:
            bucket_key = (row_date - timedelta(days=row_date.weekday())).isoformat()
        bucket = trend_map.get(bucket_key)
        if bucket is None:
            continue
        if row.status == CONFLICT_STATUS:
            bucket["conflictCount"] += 1
            continue
        bucket["scheduleHours"] += _hours(row)
        bucket["scheduleCount"] += 1
    trend = []
    for item in trend_map.values():
        item["scheduleHours"] = _round(item["scheduleHours"])
        item["utilization"] = (
            _round(item["scheduleHours"] / item["availableHours"] * 100)
            if item["availableHours"] > 0
            else 0.0
        )
        trend.append(item)
    trend.sort(key=lambda b: b["bucket"])

    # ---------------- 冲突清单 ----------------
    conflicts = []
    for row, entry in conflict_rows:
        conflicts.append(
            {
                "scheduleNo": row.schedule_no,
                "equipmentId": entry["equipmentId"],
                "equipmentNo": entry["equipmentNo"],
                "equipmentName": entry["equipmentName"],
                "taskNo": row.task_no or "",
                "taskName": row.task_name or "",
                "planStart": _t(row.plan_start),
                "planEnd": _t(row.plan_end),
                "reason": row.conflict_reason or "",
            }
        )
    conflicts.sort(key=lambda c: c["planStart"], reverse=True)
    conflicts = conflicts[:MAX_CONFLICT_ROWS]

    equipment_rows = sorted(outs, key=lambda o: (o["utilization"], o["scheduleHours"]), reverse=True)

    return {
        "range": {"from": _d(date_from), "to": _d(date_to)},
        "summary": summary,
        "byCategory": category_list,
        "byWorkshop": workshop_list,
        "equipment": equipment_rows,
        "trend": trend,
        "conflicts": conflicts,
    }


# ---------------- 端点 ----------------


@capacity_router.get("/capacity/board")
def capacity_board(
    date_from: date | None = Query(None, alias="from", description="统计开始日（含），默认最近 30 天"),
    date_to: date | None = Query(None, alias="to", description="统计结束日（含），默认今天"),
    workshop: str | None = Query(None, description="车间过滤"),
    category: str | None = Query(None, description="设备分类过滤"),
    user: User = Depends(require_perm("production:capacity:list")),
    db: Session = Depends(get_db),
):
    """产能利用率看板总览：汇总 + 分类 / 车间 / 趋势 / 设备明细 / 冲突清单。"""
    today = date.today()
    to = date_to or today
    frm = date_from or (to - timedelta(days=DEFAULT_PERIOD_DAYS - 1))
    if frm > to:
        frm, to = to, frm
    board = _build_board(db, frm, to, workshop, category)
    board["equipment"] = board["equipment"][:MAX_EQUIPMENT_ROWS]
    return board


@capacity_router.get("/capacity/equipment/{equipment_id}")
def capacity_equipment(
    equipment_id: int,
    date_from: date | None = Query(None, alias="from", description="明细开始日（含），默认最近 30 天"),
    date_to: date | None = Query(None, alias="to", description="明细结束日（含），默认今天"),
    user: User = Depends(require_perm("production:capacity:list")),
    db: Session = Depends(get_db),
):
    """单设备下钻：设备指标 + 期间排程明细 + 每日利用率曲线。"""
    today = date.today()
    to = date_to or today
    frm = date_from or (to - timedelta(days=DEFAULT_PERIOD_DAYS - 1))
    if frm > to:
        frm, to = to, frm

    board = _build_board(db, frm, to, None, None)
    target = next((o for o in board["equipment"] if o["equipmentId"] == equipment_id), None)
    if target is None:
        # 设备明细表最多返回 100 条，超出部分仍允许下钻
        ledger = _load_equipment_rows(db)
        eq = ledger.get(equipment_id)
        if eq is None:
            raise BizException(PRODUCTION_CAPACITY_NOT_FOUND, "设备不存在或不在统计范围内")
        target = {
            "equipmentId": eq.id,
            "equipmentNo": getattr(eq, "equipment_no", "") or "",
            "equipmentName": getattr(eq, "name", "") or "",
            "category": getattr(eq, "category", "other") or "other",
            "categoryText": _text(CATEGORY_CN, getattr(eq, "category", "other") or "other"),
            "workshop": getattr(eq, "workshop", "") or "",
            "status": getattr(eq, "status", "idle") or "idle",
            "statusText": _text(EQUIPMENT_STATUS_CN, getattr(eq, "status", "idle") or "idle"),
            "scheduleHours": 0.0,
            "availableHours": 0.0,
            "utilization": 0.0,
            "scheduleCount": 0,
            "conflictCount": 0,
            "taskCount": 0,
            "runHours": _round(_f(getattr(eq, "run_hours", 0))),
            "lastScheduleEnd": "",
            "overloaded": False,
        }

    start_dt = datetime.combine(frm, datetime.min.time())
    end_dt = datetime.combine(to, datetime.max.time())
    rows = list(
        db.scalars(
            select(ProdSchedule)
            .where(
                ProdSchedule.deleted == 0,
                ProdSchedule.resource_type == "equipment",
                ProdSchedule.resource_id == equipment_id,
                ProdSchedule.status.in_(OCCUPY_STATUS + (CONFLICT_STATUS,)),
                ProdSchedule.plan_start >= start_dt,
                ProdSchedule.plan_start <= end_dt,
            )
            .order_by(ProdSchedule.plan_start, ProdSchedule.id)
        ).all()
    )
    schedules = [
        {
            "id": r.id,
            "scheduleNo": r.schedule_no,
            "planNo": r.plan_no_text,
            "taskId": r.task_id,
            "taskNo": r.task_no,
            "taskName": r.task_name,
            "resourceCode": r.resource_code,
            "resourceName": r.resource_name,
            "planStart": _t(r.plan_start),
            "planEnd": _t(r.plan_end),
            "durationHours": _round(_hours(r)),
            "status": r.status,
            "statusText": _text(SCHEDULE_STATUS_CN, r.status),
            "conflictReason": r.conflict_reason or "",
        }
        for r in rows
    ]

    # 每日利用率曲线（metrics）
    available_per_day = 24 * _availability_factor(target.get("status") or "idle")
    metrics = []
    for key, eff_start, eff_end in _bucket_plan(frm, to, False):
        span = (eff_end - eff_start).days + 1
        metrics.append(
            {
                "bucket": key.isoformat(),
                "scheduleHours": 0.0,
                "availableHours": _round(span * available_per_day),
                "utilization": 0.0,
                "scheduleCount": 0,
                "conflictCount": 0,
            }
        )
    metric_map = {m["bucket"]: m for m in metrics}
    for r in rows:
        if not r.plan_start:
            continue
        m = metric_map.get(r.plan_start.date().isoformat())
        if m is None:
            continue
        if r.status == CONFLICT_STATUS:
            m["conflictCount"] += 1
            continue
        m["scheduleHours"] += _hours(r)
        m["scheduleCount"] += 1
    for m in metrics:
        m["scheduleHours"] = _round(m["scheduleHours"])
        m["utilization"] = (
            _round(m["scheduleHours"] / m["availableHours"] * 100) if m["availableHours"] > 0 else 0.0
        )

    return {"equipment": target, "schedules": schedules, "metrics": metrics}
