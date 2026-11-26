"""B6 设备台账 / 能耗采集 / 设备预警路由。

与 `asset.router` / `asset.finance_router` / `asset.bom_router` 同前缀 `/asset`，
业务域同为 asset（`main.py` 里以 `prefix="/api/v1"` 挂载）。

覆盖三块：
- 设备台账：`/asset/equipments`（增删改查 + 计数 + 详情）
- 能耗 / 运行数据：`/asset/equipment-metrics`
- 设备预警：`/asset/equipment-alerts`（手工登记 + 处理 + 规则扫描）
- 看板聚合：`/asset/equipment-board`
"""

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import recycle
from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.asset import service as svc
from app.modules.asset.equipment_models import Equipment, EquipmentAlert, EquipmentMetric
from app.modules.asset.equipment_schemas import (
    EquipmentAlertHandleIn,
    EquipmentAlertIn,
    EquipmentIn,
    EquipmentMetricIn,
)
from app.modules.auth.models import User
from app.services import numbering

equipment_router = APIRouter(prefix="/asset", tags=["asset"], route_class=EnvelopeRoute)

# ---------------- 口径常量 ----------------

EQUIPMENT_STATUS_CN = {
    "idle": "闲置",
    "running": "运行中",
    "maintenance": "维护中",
    "fault": "故障",
    "scrapped": "已报废",
}

EQUIPMENT_CATEGORY_CN = {
    "wind_tunnel": "风洞",
    "cfd": "CFD 计算",
    "machining": "加工中心",
    "test": "试验台",
    "other": "其他",
}

SHIFT_CN = {"morning": "早班", "day": "白班", "night": "夜班"}

METRIC_SOURCE_CN = {"manual": "手工录入", "schedule": "排程推算"}

ALERT_RULE_CN = {
    "maintain_overdue": "保养逾期",
    "energy_abnormal": "能耗异常",
    "low_utilization": "利用率偏低",
    "fault": "设备故障",
    "status_abnormal": "状态异常",
}

ALERT_LEVEL_CN = {"info": "提示", "warning": "警告", "critical": "严重"}

ALERT_STATUS_CN = {"open": "待处理", "processing": "处理中", "closed": "已关闭"}

# 扫描阈值：利用率 = 8 小时/天 × 30 天 × 30% = 72 小时；能耗异常 = 近 30 天均值 × 1.5
UTILIZATION_BASE_HOURS_PER_DAY = 8.0
UTILIZATION_WINDOW_DAYS = 30
UTILIZATION_MIN_RATIO = 0.30
ENERGY_ABNORMAL_FACTOR = 1.5
ENERGY_MIN_SAMPLE_DAYS = 3


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    return v or ""


def _d(v) -> str:
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _n(v) -> float | None:
    return float(v) if v is not None else None


def _text(mapping: dict[str, str], value: str | None) -> str:
    key = value or ""
    return mapping.get(key, key)


def _counts(db: Session, model, keys: tuple[str, ...]) -> dict:
    """按状态统计（含 all 合计），未命中的状态补 0。"""
    rows = db.execute(
        select(model.status, func.count()).where(model.deleted == 0).group_by(model.status)
    ).all()
    data: dict[str, int] = {key: 0 for key in keys}
    total = 0
    for status, cnt in rows:
        total += int(cnt)
        if status in data:
            data[status] = int(cnt)
    data["all"] = total
    return data


def _parse_day(raw: str, fallback: date) -> date:
    raw = (raw or "").strip()
    if not raw:
        return fallback
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise BizException(R.GENERIC_PARAM, f"非法日期格式：{raw}")


# ---------------- 序列化 ----------------


def _equipment_out(e: Equipment) -> dict:
    return {
        "id": e.id,
        "equipmentNo": e.equipment_no,
        "name": e.name,
        "category": e.category or "",
        "categoryText": _text(EQUIPMENT_CATEGORY_CN, e.category),
        "model": e.model or "",
        "spec": e.spec or "",
        "workshop": e.workshop or "",
        "location": e.location or "",
        "vendorId": e.vendor_id,
        "vendorName": e.vendor_name or "",
        "purchaseDate": _d(e.purchase_date),
        "commissionDate": _d(e.commission_date),
        "originalValue": _n(e.original_value),
        "status": e.status,
        "statusText": _text(EQUIPMENT_STATUS_CN, e.status),
        "ownerId": e.owner_id,
        "ownerName": e.owner_name or "",
        "deptId": e.dept_id,
        "deptName": e.dept_name or "",
        "maintainCycleDays": int(e.maintain_cycle_days or 0),
        "lastMaintainDate": _d(e.last_maintain_date),
        "nextMaintainDate": _d(e.next_maintain_date),
        "runHours": _n(e.run_hours),
        "remark": e.remark or "",
        "version": e.version,
        "createTime": _t(e.create_time),
        "updateTime": _t(e.update_time),
    }


def _metric_out(m: EquipmentMetric) -> dict:
    return {
        "id": m.id,
        "equipmentId": m.equipment_id,
        "equipmentNo": m.equipment_no or "",
        "equipmentName": m.equipment_name or "",
        "statDate": _d(m.stat_date),
        "shift": m.shift or "",
        "shiftText": _text(SHIFT_CN, m.shift),
        "runHours": _n(m.run_hours),
        "downtimeHours": _n(m.downtime_hours),
        "energy": _n(m.energy),
        "outputQty": _n(m.output_qty),
        "source": m.source or "",
        "sourceText": _text(METRIC_SOURCE_CN, m.source),
        "remark": m.remark or "",
        "createTime": _t(m.create_time),
    }


def _alert_out(a: EquipmentAlert) -> dict:
    return {
        "id": a.id,
        "alertNo": a.alert_no,
        "equipmentId": a.equipment_id,
        "equipmentNo": a.equipment_no or "",
        "equipmentName": a.equipment_name or "",
        "ruleType": a.rule_type or "",
        "ruleTypeText": _text(ALERT_RULE_CN, a.rule_type),
        "level": a.level or "",
        "levelText": _text(ALERT_LEVEL_CN, a.level),
        "title": a.title or "",
        "content": a.content or "",
        "status": a.status,
        "statusText": _text(ALERT_STATUS_CN, a.status),
        "triggeredAt": _t(a.triggered_at),
        "handlerId": a.handler_id,
        "handlerName": a.handler_name or "",
        "handledAt": _t(a.handled_at) if a.handled_at else "",
        "handleResult": a.handle_result or "",
        "remark": a.remark or "",
        "createTime": _t(a.create_time),
    }


# ---------------- 设备台账 ----------------


def _equipment_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(Equipment),
        Equipment,
        request.query_params,
        db,
        page,
        search_cols=["equipment_no", "name", "model", "spec"],
        filter_cols={"status", "category", "workshop", "dept_id", "vendor_id"},
        range_cols={"purchase_date", "commission_date", "next_maintain_date"},
        sort_cols={
            "id",
            "equipment_no",
            "name",
            "category",
            "status",
            "purchase_date",
            "next_maintain_date",
            "create_time",
        },
    )


@equipment_router.get("/equipments")
def list_equipments(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:equipment:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _equipment_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_equipment_out(e) for e in rows], "total": total, "page": page, "size": size}


@equipment_router.get("/equipments/counts")
def equipment_counts(
    user: User = Depends(require_perm("asset:equipment:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, Equipment, ("idle", "running", "maintenance", "fault", "scrapped"))


@equipment_router.get("/equipments/{eid}")
def get_equipment(
    eid: int,
    user: User = Depends(require_perm("asset:equipment:list")),
    db: Session = Depends(get_db),
):
    e = db.get(Equipment, eid)
    if not e or e.deleted:
        raise BizException(R.ASSET_EQUIPMENT_NOT_FOUND, "设备不存在")
    data = _equipment_out(e)
    metrics = db.scalars(
        select(EquipmentMetric)
        .where(EquipmentMetric.equipment_id == eid, EquipmentMetric.deleted == 0)
        .order_by(EquipmentMetric.stat_date.desc(), EquipmentMetric.id.desc())
        .limit(30)
    ).all()
    data["metrics"] = [_metric_out(m) for m in metrics]
    alerts = db.scalars(
        select(EquipmentAlert)
        .where(
            EquipmentAlert.equipment_id == eid,
            EquipmentAlert.deleted == 0,
            EquipmentAlert.status != "closed",
        )
        .order_by(EquipmentAlert.id.desc())
        .limit(50)
    ).all()
    data["alerts"] = [_alert_out(a) for a in alerts]
    return data


@equipment_router.post("/equipments", status_code=201)
def create_equipment(
    body: EquipmentIn,
    current: User = Depends(require_perm("asset:equipment:create")),
    db: Session = Depends(get_db),
):
    dup = db.scalar(select(Equipment.id).where(Equipment.equipment_no == body.equipment_no, Equipment.deleted == 0))
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "设备编号已存在")
    vendor_name = svc.load_supplier_name(db, body.vendor_id)
    e = Equipment(
        equipment_no=body.equipment_no,
        name=body.name,
        category=body.category,
        model=body.model,
        spec=body.spec,
        workshop=body.workshop,
        location=body.location,
        vendor_id=body.vendor_id,
        vendor_name=vendor_name,
        purchase_date=body.purchase_date,
        commission_date=body.commission_date,
        original_value=body.original_value,
        status=body.status,
        owner_id=body.owner_id,
        owner_name=body.owner_name,
        dept_id=body.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id),
        maintain_cycle_days=body.maintain_cycle_days,
        last_maintain_date=body.last_maintain_date,
        next_maintain_date=body.next_maintain_date,
        run_hours=body.run_hours,
        remark=body.remark,
        create_by=current.id,
    )
    db.add(e)
    db.flush()
    audit(
        db,
        user_id=current.id,
        module="asset",
        action="equipment_create",
        biz_type="equipment",
        biz_id=e.id,
        detail={"equipmentNo": e.equipment_no},
    )
    db.commit()
    return _equipment_out(e)


@equipment_router.put("/equipments/{eid}")
def update_equipment(
    eid: int,
    body: EquipmentIn,
    current: User = Depends(require_perm("asset:equipment:edit")),
    db: Session = Depends(get_db),
):
    e = db.get(Equipment, eid)
    if not e or e.deleted:
        raise BizException(R.ASSET_EQUIPMENT_NOT_FOUND, "设备不存在")
    svc.check_version(e, body.version)
    dup = db.scalar(
        select(Equipment.id).where(
            Equipment.equipment_no == body.equipment_no, Equipment.id != eid, Equipment.deleted == 0
        )
    )
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "设备编号已存在")
    e.equipment_no = body.equipment_no
    e.name = body.name
    e.category = body.category
    e.model = body.model
    e.spec = body.spec
    e.workshop = body.workshop
    e.location = body.location
    e.vendor_id = body.vendor_id
    e.vendor_name = svc.load_supplier_name(db, body.vendor_id)
    e.purchase_date = body.purchase_date
    e.commission_date = body.commission_date
    e.original_value = body.original_value
    e.status = body.status
    e.owner_id = body.owner_id
    e.owner_name = body.owner_name
    e.dept_id = body.dept_id
    e.dept_name = svc.load_dept_name(db, body.dept_id)
    e.maintain_cycle_days = body.maintain_cycle_days
    e.last_maintain_date = body.last_maintain_date
    e.next_maintain_date = body.next_maintain_date
    e.run_hours = body.run_hours
    e.remark = body.remark
    e.version = (e.version or 0) + 1
    e.update_by = current.id
    e.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="asset",
        action="equipment_edit",
        biz_type="equipment",
        biz_id=eid,
    )
    db.commit()
    return _equipment_out(e)


@equipment_router.delete("/equipments/{eid}")
def delete_equipment(
    eid: int,
    current: User = Depends(require_perm("asset:equipment:delete")),
    db: Session = Depends(get_db),
):
    e = db.get(Equipment, eid)
    if not e or e.deleted:
        raise BizException(R.ASSET_EQUIPMENT_NOT_FOUND, "设备不存在")
    recycle.soft_delete(
        db,
        Equipment,
        e,
        user=current,
        module="asset",
        resource="Equipment",
        restore_fields={"equipment_no": e.equipment_no},
    )
    # equipment_no 有物理唯一索引，逻辑删后释放编号，避免同名重建触发唯一键冲突
    suffix = f"#del{e.id}"
    e.equipment_no = f"{e.equipment_no[: max(1, 32 - len(suffix))]}{suffix}"
    e.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="asset",
        action="equipment_delete",
        biz_type="equipment",
        biz_id=eid,
    )
    db.commit()
    return None


# ---------------- 能耗 / 运行数据 ----------------


@equipment_router.get("/equipment-metrics")
def list_equipment_metrics(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:equipment:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(EquipmentMetric),
        EquipmentMetric,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["equipment_no", "equipment_name"],
        filter_cols={"equipment_id", "shift", "source"},
        range_cols={"stat_date"},
        sort_cols={"id", "stat_date", "energy", "run_hours", "create_time"},
        default_sort=("stat_date", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_metric_out(m) for m in rows], "total": total, "page": page, "size": size}


@equipment_router.post("/equipment-metrics", status_code=201)
def create_equipment_metric(
    body: EquipmentMetricIn,
    current: User = Depends(require_perm("asset:equipment:metric:create")),
    db: Session = Depends(get_db),
):
    e = db.get(Equipment, body.equipment_id)
    if not e or e.deleted:
        raise BizException(R.ASSET_EQUIPMENT_NOT_FOUND, "设备不存在")
    metric = EquipmentMetric(
        equipment_id=e.id,
        equipment_no=e.equipment_no,
        equipment_name=e.name,
        stat_date=body.stat_date or date.today(),
        shift=body.shift,
        run_hours=body.run_hours,
        downtime_hours=body.downtime_hours,
        energy=body.energy,
        output_qty=body.output_qty,
        source=body.source,
        remark=body.remark,
        create_by=current.id,
    )
    db.add(metric)
    # 累计运行工时随采集数据累加（台账口径）
    e.run_hours = float(e.run_hours or 0) + float(body.run_hours or 0)
    e.update_time = datetime.now()
    db.flush()
    audit(
        db,
        user_id=current.id,
        module="asset",
        action="equipment_metric_create",
        biz_type="equipment_metric",
        biz_id=metric.id,
        detail={"equipmentNo": e.equipment_no},
    )
    db.commit()
    return _metric_out(metric)


# ---------------- 设备预警 ----------------


def _next_alert_no(db: Session) -> str:
    """预警单号：走统一编号服务；计数器落后于存量数据时逐号试探跳过已占用号。

    编号规则未注册时兜底生��� `EA+日期+流水`，避免整个预警功能不可用。
    """
    try:
        for _ in range(100):
            no = numbering.next_no(db, "equipment_alert")
            taken = db.scalar(select(EquipmentAlert.id).where(EquipmentAlert.alert_no == no).limit(1))
            if taken is None:
                return no
    except BizException:
        pass
    base = f"EA{datetime.now():%Y%m%d}"
    for i in range(1, 10000):
        no = f"{base}{i:04d}"
        taken = db.scalar(select(EquipmentAlert.id).where(EquipmentAlert.alert_no == no).limit(1))
        if taken is None:
            return no
    raise BizException(R.ADMIN_NUMBER_CONFLICT, "预警单号生成失败")


@equipment_router.get("/equipment-alerts")
def list_equipment_alerts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:equipment:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(EquipmentAlert),
        EquipmentAlert,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["alert_no", "equipment_no", "equipment_name", "title"],
        filter_cols={"equipment_id", "rule_type", "level", "status"},
        range_cols={"triggered_at"},
        sort_cols={"id", "alert_no", "level", "rule_type", "status", "triggered_at", "create_time"},
        default_sort=("triggered_at", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_alert_out(a) for a in rows], "total": total, "page": page, "size": size}


@equipment_router.get("/equipment-alerts/counts")
def equipment_alert_counts(
    user: User = Depends(require_perm("asset:equipment:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, EquipmentAlert, ("open", "processing", "closed"))


@equipment_router.post("/equipment-alerts", status_code=201)
def create_equipment_alert(
    body: EquipmentAlertIn,
    current: User = Depends(require_perm("asset:equipment:alert:create")),
    db: Session = Depends(get_db),
):
    e = db.get(Equipment, body.equipment_id)
    if not e or e.deleted:
        raise BizException(R.ASSET_EQUIPMENT_NOT_FOUND, "设备不存在")
    alert = EquipmentAlert(
        alert_no=_next_alert_no(db),
        equipment_id=e.id,
        equipment_no=e.equipment_no,
        equipment_name=e.name,
        rule_type=body.rule_type,
        level=body.level,
        title=body.title or f"{e.name} {_text(ALERT_RULE_CN, body.rule_type)}",
        content=body.content,
        status="open",
        triggered_at=datetime.now(),
        remark=body.remark,
        create_by=current.id,
    )
    db.add(alert)
    db.flush()
    audit(
        db,
        user_id=current.id,
        module="asset",
        action="equipment_alert_create",
        biz_type="equipment_alert",
        biz_id=alert.id,
        detail={"alertNo": alert.alert_no},
    )
    db.commit()
    return _alert_out(alert)


@equipment_router.post("/equipment-alerts/{aid}/handle")
def handle_equipment_alert(
    aid: int,
    body: EquipmentAlertHandleIn,
    current: User = Depends(require_perm("asset:equipment:alert:handle")),
    db: Session = Depends(get_db),
):
    alert = db.get(EquipmentAlert, aid)
    if not alert or alert.deleted:
        raise BizException(R.ASSET_EQUIPMENT_NOT_FOUND, "预警记录不存在")
    if body.status not in ("processing", "closed"):
        raise BizException(R.ASSET_EQUIPMENT_ALERT_INVALID_STATE, "预警状态只能是处理中或已关闭")
    if alert.status == "closed":
        raise BizException(R.ASSET_EQUIPMENT_ALERT_INVALID_STATE, "该预警已关闭，不能重复处理")
    alert.status = body.status
    alert.handler_id = current.id
    alert.handler_name = current.name or ""
    alert.handled_at = datetime.now()
    alert.handle_result = body.handle_result
    alert.update_by = current.id
    alert.update_time = datetime.now()
    audit(
        db,
        user_id=current.id,
        module="asset",
        action="equipment_alert_handle",
        biz_type="equipment_alert",
        biz_id=aid,
        detail={"status": body.status},
    )
    db.commit()
    return _alert_out(alert)


def _scan_rules(db: Session, e: Equipment, today: date, window_start: date) -> list[tuple[str, str, str, str]]:
    """按规则算出该设备当前命中的预警（rule_type, level, title, content）。"""
    hits: list[tuple[str, str, str, str]] = []

    # ① 保养逾期：下次保养日期早于今天
    if e.next_maintain_date and e.next_maintain_date < today:
        hits.append(
            (
                "maintain_overdue",
                "warning",
                f"{e.name} 保养逾期",
                f"设备下次保养日期为 {e.next_maintain_date}，已逾期，请及时安排保养。",
            )
        )

    rows = db.execute(
        select(EquipmentMetric.stat_date, func.sum(EquipmentMetric.energy))
        .where(
            EquipmentMetric.equipment_id == e.id,
            EquipmentMetric.deleted == 0,
            EquipmentMetric.stat_date >= window_start,
            EquipmentMetric.stat_date <= today,
        )
        .group_by(EquipmentMetric.stat_date)
        .order_by(EquipmentMetric.stat_date.desc())
    ).all()
    if not rows:
        # 窗口内没有任何采集数据 —— 不判定利用率与能耗，避免误报
        return hits

    # ② 利用率偏低：近 30 天运行工时之和 < 8h/天 × 30 天 × 30%
    run_sum = float(
        db.scalar(
            select(func.coalesce(func.sum(EquipmentMetric.run_hours), 0)).where(
                EquipmentMetric.equipment_id == e.id,
                EquipmentMetric.deleted == 0,
                EquipmentMetric.stat_date >= window_start,
                EquipmentMetric.stat_date <= today,
            )
        )
        or 0
    )
    threshold = UTILIZATION_BASE_HOURS_PER_DAY * UTILIZATION_WINDOW_DAYS * UTILIZATION_MIN_RATIO
    if run_sum < threshold:
        hits.append(
            (
                "low_utilization",
                "info",
                f"{e.name} 利用率偏低",
                f"近 {UTILIZATION_WINDOW_DAYS} 天累计运行 {run_sum:.1f} 小时，低于阈值 {threshold:.0f} 小时。",
            )
        )

    # ③ 能耗异常：同日能耗 > 近 30 天均值 × 1.5（同一设备同规则只出一条，取最近异常日）
    if len(rows) >= ENERGY_MIN_SAMPLE_DAYS:
        avg = sum(float(r[1] or 0) for r in rows) / len(rows)
        if avg > 0:
            for stat_date, energy in rows:
                value = float(energy or 0)
                if value > avg * ENERGY_ABNORMAL_FACTOR:
                    hits.append(
                        (
                            "energy_abnormal",
                            "warning",
                            f"{e.name} 能耗异常",
                            f"{stat_date} 能耗 {value:.1f} kWh，超过近 30 天均值 {avg:.1f} kWh 的 "
                            f"{ENERGY_ABNORMAL_FACTOR} 倍。",
                        )
                    )
                    break
    return hits


@equipment_router.post("/equipment-alerts/scan")
def scan_equipment_alerts(
    current: User = Depends(require_perm("asset:equipment:alert:create")),
    db: Session = Depends(get_db),
):
    """预警扫描：按规则生成预警。**幂等** —— 同设备同规则已有未关闭预警则跳过。"""
    today = date.today()
    window_start = today - timedelta(days=UTILIZATION_WINDOW_DAYS)

    equipments = db.scalars(select(Equipment).where(Equipment.deleted == 0).order_by(Equipment.id)).all()
    open_rows = db.execute(
        select(EquipmentAlert.equipment_id, EquipmentAlert.rule_type).where(
            EquipmentAlert.deleted == 0, EquipmentAlert.status != "closed"
        )
    ).all()
    open_set = {(int(r[0]), r[1]) for r in open_rows}

    created = 0
    skipped = 0
    new_alerts: list[EquipmentAlert] = []
    for e in equipments:
        if e.status == "scrapped":
            continue
        for rule_type, level, title, content in _scan_rules(db, e, today, window_start):
            key = (e.id, rule_type)
            if key in open_set:
                skipped += 1
                continue
            alert = EquipmentAlert(
                alert_no=_next_alert_no(db),
                equipment_id=e.id,
                equipment_no=e.equipment_no,
                equipment_name=e.name,
                rule_type=rule_type,
                level=level,
                title=title,
                content=content,
                status="open",
                triggered_at=datetime.now(),
                create_by=current.id,
            )
            db.add(alert)
            open_set.add(key)
            created += 1
            new_alerts.append(alert)

    db.flush()
    audit(
        db,
        user_id=current.id,
        module="asset",
        action="equipment_alert_scan",
        biz_type="equipment_alert",
        detail={"created": created, "skipped": skipped},
    )
    db.commit()
    return {
        "created": created,
        "skipped": skipped,
        "items": [_alert_out(a) for a in new_alerts],
    }


# ---------------- 看板聚合 ----------------


@equipment_router.get("/equipment-board")
def equipment_board(
    request: Request,
    date_from: str = Query("", alias="from"),
    date_to: str = Query("", alias="to"),
    user: User = Depends(require_perm("asset:equipment:list")),
    db: Session = Depends(get_db),
):
    """设备看板聚合：状态分布 / 类别分布 / 能耗趋势 / Top5 能耗设备 / 预警级别分布 / 保养逾期数。"""
    today = date.today()
    start = _parse_day(date_from, today - timedelta(days=UTILIZATION_WINDOW_DAYS - 1))
    end = _parse_day(date_to, today)

    status_rows = db.execute(
        select(Equipment.status, func.count())
        .where(Equipment.deleted == 0)
        .group_by(Equipment.status)
        .order_by(Equipment.status)
    ).all()
    status_dist = [
        {"status": s or "", "statusText": _text(EQUIPMENT_STATUS_CN, s), "count": int(c)} for s, c in status_rows
    ]

    category_rows = db.execute(
        select(Equipment.category, func.count())
        .where(Equipment.deleted == 0)
        .group_by(Equipment.category)
        .order_by(Equipment.category)
    ).all()
    category_dist = [
        {
            "category": c or "",
            "categoryText": _text(EQUIPMENT_CATEGORY_CN, c),
            "count": int(n),
        }
        for c, n in category_rows
    ]

    trend_rows = db.execute(
        select(EquipmentMetric.stat_date, func.sum(EquipmentMetric.energy))
        .where(
            EquipmentMetric.deleted == 0,
            EquipmentMetric.stat_date >= start,
            EquipmentMetric.stat_date <= end,
        )
        .group_by(EquipmentMetric.stat_date)
        .order_by(EquipmentMetric.stat_date)
    ).all()
    energy_trend = [
        {"statDate": _d(d), "energy": float(e or 0)} for d, e in trend_rows
    ]

    top_rows = db.execute(
        select(
            EquipmentMetric.equipment_id,
            EquipmentMetric.equipment_no,
            EquipmentMetric.equipment_name,
            func.sum(EquipmentMetric.energy),
        )
        .where(
            EquipmentMetric.deleted == 0,
            EquipmentMetric.stat_date >= start,
            EquipmentMetric.stat_date <= end,
        )
        .group_by(EquipmentMetric.equipment_id, EquipmentMetric.equipment_no, EquipmentMetric.equipment_name)
        .order_by(func.sum(EquipmentMetric.energy).desc())
        .limit(5)
    ).all()
    top_energy = [
        {
            "equipmentId": int(r[0]),
            "equipmentNo": r[1] or "",
            "equipmentName": r[2] or "",
            "energy": float(r[3] or 0),
        }
        for r in top_rows
    ]

    level_rows = db.execute(
        select(EquipmentAlert.level, func.count())
        .where(EquipmentAlert.deleted == 0)
        .group_by(EquipmentAlert.level)
        .order_by(EquipmentAlert.level)
    ).all()
    alert_level_dist = [
        {"level": lv or "", "levelText": _text(ALERT_LEVEL_CN, lv), "count": int(c)} for lv, c in level_rows
    ]

    overdue = db.scalar(
        select(func.count())
        .select_from(Equipment)
        .where(
            Equipment.deleted == 0,
            Equipment.next_maintain_date.is_not(None),
            Equipment.next_maintain_date < today,
            Equipment.status != "scrapped",
        )
    )

    total_energy = sum(item["energy"] for item in energy_trend)
    return {
        "from": _d(start),
        "to": _d(end),
        "totalEquipments": sum(item["count"] for item in status_dist),
        "statusDist": status_dist,
        "categoryDist": category_dist,
        "energyTrend": energy_trend,
        "totalEnergy": round(total_energy, 2),
        "topEnergy": top_energy,
        "alertLevelDist": alert_level_dist,
        "maintainOverdueCount": int(overdue or 0),
    }


__all__ = ["equipment_router"]
