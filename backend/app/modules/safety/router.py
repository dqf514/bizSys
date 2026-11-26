"""安全巡检域（B8 / CSV 24）路由，前缀 /api/v1/safety。

三件套：巡检计划 → 巡检记录（提交时自动生成隐患）→ 隐患整改闭环（整改 → 验证 → 关闭）。
"""

from datetime import date, datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common import recycle
from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_any_perm, require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.safety import schemas as S
from app.modules.safety import service as svc
from app.modules.safety.models import SafetyHazard, SafetyInspection, SafetyInspectionPlan

router = APIRouter(prefix="/safety", tags=["safety"], route_class=EnvelopeRoute)

# 兼容变量名：主程序按 `safety_router` 引入
safety_router = router


# ---------------- 序列化 ----------------


def _t(v) -> str:
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _out_plan(p: SafetyInspectionPlan) -> dict:
    return {
        "id": p.id,
        "planNo": p.plan_no,
        "name": p.name,
        "planType": p.plan_type,
        "planTypeText": svc.PLAN_TYPE_CN.get(p.plan_type, p.plan_type),
        "targetArea": p.target_area,
        "checkItems": svc.plan_items(p),
        "cycleDays": p.cycle_days,
        "nextDate": _t(p.next_date),
        "ownerId": p.owner_id,
        "ownerName": p.owner_name,
        "deptId": p.dept_id,
        "deptName": p.dept_name,
        "status": p.status,
        "statusText": svc.PLAN_STATUS_CN.get(p.status, p.status),
        "remark": p.remark or "",
        "createTime": _t(p.create_time),
        "updateTime": _t(p.update_time),
    }


def _out_inspection(r: SafetyInspection) -> dict:
    return {
        "id": r.id,
        "recordNo": r.record_no,
        "planId": r.plan_id,
        "planName": r.plan_name,
        "area": r.area,
        "inspectDate": _t(r.inspect_date),
        "inspectorId": r.inspector_id,
        "inspectorName": r.inspector_name,
        "result": r.result,
        "resultText": svc.INSPECTION_RESULT_CN.get(r.result, r.result),
        "abnormalCount": r.abnormal_count,
        "items": svc.parse_items(r.items_json),
        "status": r.status,
        "statusText": svc.INSPECTION_STATUS_CN.get(r.status, r.status),
        "summary": r.summary or "",
        "remark": r.remark or "",
        "createTime": _t(r.create_time),
        "updateTime": _t(r.update_time),
    }


def _out_hazard(h: SafetyHazard) -> dict:
    return {
        "id": h.id,
        "hazardNo": h.hazard_no,
        "inspectionId": h.inspection_id,
        "recordNo": h.record_no,
        "source": h.source,
        "sourceText": svc.HAZARD_SOURCE_CN.get(h.source, h.source),
        "description": h.description or "",
        "level": h.level,
        "levelText": svc.HAZARD_LEVEL_CN.get(h.level, h.level),
        "status": h.status,
        "statusText": svc.HAZARD_STATUS_CN.get(h.status, h.status),
        "responsibleId": h.responsible_id,
        "responsibleName": h.responsible_name,
        "deadline": _t(h.deadline),
        "foundAt": _t(h.found_at),
        "measure": h.measure or "",
        "rectifiedAt": _t(h.rectified_at),
        "rectifiedByName": h.rectified_by_name or "",
        "verifyResult": h.verify_result or "",
        "verifyByName": h.verify_by_name or "",
        "verifiedAt": _t(h.verified_at),
        "overdue": svc.is_overdue(h),
        "remark": h.remark or "",
        "createTime": _t(h.create_time),
        "updateTime": _t(h.update_time),
    }


def _load_plan(db: Session, pid: int) -> SafetyInspectionPlan:
    p = db.get(SafetyInspectionPlan, pid)
    if not p or p.deleted:
        raise BizException(R.SAFETY_NOT_FOUND, "巡检计划不存在")
    return p


def _load_inspection(db: Session, rid: int) -> SafetyInspection:
    r = db.get(SafetyInspection, rid)
    if not r or r.deleted:
        raise BizException(R.SAFETY_NOT_FOUND, "巡检记录不存在")
    return r


def _load_hazard(db: Session, hid: int) -> SafetyHazard:
    h = db.get(SafetyHazard, hid)
    if not h or h.deleted:
        raise BizException(R.SAFETY_NOT_FOUND, "隐患不存在")
    return h


# ---------------- 巡检计划 ----------------


@router.get("/plans")
def list_plans(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("safety:inspection:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(SafetyInspectionPlan),
        SafetyInspectionPlan,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["plan_no", "name", "target_area"],
        filter_cols={"status", "plan_type"},
        range_cols={"next_date"},
        sort_cols={"id", "plan_no", "name", "plan_type", "next_date", "status", "create_time"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_out_plan(p) for p in rows], "total": total, "page": page, "size": size}


@router.get("/plans/counts")
def plan_counts(
    user: User = Depends(require_perm("safety:inspection:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(SafetyInspectionPlan.status, func.count())
        .where(SafetyInspectionPlan.deleted == 0)
        .group_by(SafetyInspectionPlan.status)
    ).all()
    data = {s: 0 for s in svc.PLAN_STATUSES}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/plans/{pid}")
def get_plan(
    pid: int,
    user: User = Depends(require_perm("safety:inspection:list")),
    db: Session = Depends(get_db),
):
    return _out_plan(_load_plan(db, pid))


@router.post("/plans", status_code=201)
def create_plan(
    body: S.PlanIn,
    current: User = Depends(require_perm("safety:inspection:create")),
    db: Session = Depends(get_db),
):
    plan_no = (body.plan_no or "").strip() or svc.next_plan_no(db)
    svc.ensure_no_available(db, SafetyInspectionPlan, "plan_no", plan_no, "计划编号")
    p = SafetyInspectionPlan(
        plan_no=plan_no,
        name=body.name,
        plan_type=body.plan_type,
        target_area=body.target_area,
        check_items=body.check_items,
        cycle_days=body.cycle_days,
        next_date=body.next_date,
        owner_id=body.owner_id,
        owner_name=body.owner_name,
        dept_id=body.dept_id,
        dept_name=body.dept_name,
        status=body.status,
        remark=body.remark,
    )
    db.add(p)
    db.flush()
    audit(
        db, user_id=current.id, module="safety", action="plan_create",
        biz_type="safety_inspection_plan", biz_id=p.id, detail={"planNo": p.plan_no, "name": p.name},
    )
    db.commit()
    return _out_plan(p)


@router.put("/plans/{pid}")
def update_plan(
    pid: int,
    body: S.PlanIn,
    current: User = Depends(require_perm("safety:inspection:edit")),
    db: Session = Depends(get_db),
):
    p = _load_plan(db, pid)
    plan_no = (body.plan_no or "").strip()
    if plan_no and plan_no != p.plan_no:
        svc.ensure_no_available(db, SafetyInspectionPlan, "plan_no", plan_no, "计划编号")
        p.plan_no = plan_no
    p.name = body.name
    p.plan_type = body.plan_type
    p.target_area = body.target_area
    p.check_items = body.check_items
    p.cycle_days = body.cycle_days
    p.next_date = body.next_date
    p.owner_id = body.owner_id
    p.owner_name = body.owner_name
    p.dept_id = body.dept_id
    p.dept_name = body.dept_name
    p.status = body.status
    p.remark = body.remark
    audit(
        db, user_id=current.id, module="safety", action="plan_update",
        biz_type="safety_inspection_plan", biz_id=p.id, detail={"planNo": p.plan_no},
    )
    db.commit()
    return _out_plan(p)


@router.delete("/plans/{pid}")
def delete_plan(
    pid: int,
    current: User = Depends(require_perm("safety:inspection:delete")),
    db: Session = Depends(get_db),
):
    p = _load_plan(db, pid)
    recycle.soft_delete(db, SafetyInspectionPlan, p, user=current, module="safety", resource="SafetyInspectionPlan")
    audit(
        db, user_id=current.id, module="safety", action="plan_delete",
        biz_type="safety_inspection_plan", biz_id=p.id, detail={"planNo": p.plan_no},
    )
    db.commit()
    return {"id": pid}


# ---------------- 巡检记录 ----------------


@router.get("/inspections")
def list_inspections(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("safety:inspection:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(SafetyInspection),
        SafetyInspection,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["record_no", "area", "inspector_name"],
        filter_cols={"status", "result", "plan_id"},
        range_cols={"inspect_date"},
        sort_cols={"id", "record_no", "area", "inspect_date", "result", "status", "create_time"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_out_inspection(r) for r in rows], "total": total, "page": page, "size": size}


@router.get("/inspections/counts")
def inspection_counts(
    user: User = Depends(require_perm("safety:inspection:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(SafetyInspection.status, func.count())
        .where(SafetyInspection.deleted == 0)
        .group_by(SafetyInspection.status)
    ).all()
    data = {s: 0 for s in svc.INSPECTION_STATUSES}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    return data


@router.get("/inspections/{rid}")
def get_inspection(
    rid: int,
    user: User = Depends(require_perm("safety:inspection:list")),
    db: Session = Depends(get_db),
):
    r = _load_inspection(db, rid)
    data = _out_inspection(r)
    hazards = db.scalars(
        select(SafetyHazard)
        .where(SafetyHazard.inspection_id == rid, SafetyHazard.deleted == 0)
        .order_by(SafetyHazard.id.asc())
    ).all()
    data["hazards"] = [_out_hazard(h) for h in hazards]
    return data


@router.post("/inspections", status_code=201)
def create_inspection(
    body: S.InspectionIn,
    current: User = Depends(require_perm("safety:inspection:create")),
    db: Session = Depends(get_db),
):
    record_no = (body.record_no or "").strip() or svc.next_record_no(db)
    svc.ensure_no_available(db, SafetyInspection, "record_no", record_no, "记录编号")
    plan = db.get(SafetyInspectionPlan, body.plan_id) if body.plan_id else None
    if body.plan_id and (not plan or plan.deleted):
        raise BizException(R.SAFETY_NOT_FOUND, "巡检计划不存在")
    r = SafetyInspection(
        record_no=record_no,
        plan_id=body.plan_id,
        plan_name=body.plan_name or (plan.name if plan else ""),
        area=body.area or (plan.target_area if plan else ""),
        inspect_date=body.inspect_date,
        inspector_id=body.inspector_id,
        inspector_name=body.inspector_name,
        result=body.result,
        abnormal_count=body.abnormal_count,
        items_json=body.items_json,
        status=body.status,
        summary=body.summary,
        remark=body.remark,
    )
    svc.recalc_result(r)
    db.add(r)
    db.flush()
    audit(
        db, user_id=current.id, module="safety", action="inspection_create",
        biz_type="safety_inspection", biz_id=r.id,
        detail={"recordNo": r.record_no, "result": r.result},
    )
    db.commit()
    return _out_inspection(r)


@router.put("/inspections/{rid}")
def update_inspection(
    rid: int,
    body: S.InspectionIn,
    current: User = Depends(require_perm("safety:inspection:edit")),
    db: Session = Depends(get_db),
):
    r = _load_inspection(db, rid)
    if r.status != "draft":
        raise BizException(R.SAFETY_INVALID_STATE, "已提交的巡检记录不能修改")
    record_no = (body.record_no or "").strip()
    if record_no and record_no != r.record_no:
        svc.ensure_no_available(db, SafetyInspection, "record_no", record_no, "记录编号")
        r.record_no = record_no
    r.plan_id = body.plan_id
    r.plan_name = body.plan_name
    r.area = body.area
    r.inspect_date = body.inspect_date
    r.inspector_id = body.inspector_id
    r.inspector_name = body.inspector_name
    r.items_json = body.items_json
    r.summary = body.summary
    r.remark = body.remark
    svc.recalc_result(r)
    audit(
        db, user_id=current.id, module="safety", action="inspection_update",
        biz_type="safety_inspection", biz_id=r.id, detail={"recordNo": r.record_no},
    )
    db.commit()
    return _out_inspection(r)


@router.delete("/inspections/{rid}")
def delete_inspection(
    rid: int,
    current: User = Depends(require_perm("safety:inspection:delete")),
    db: Session = Depends(get_db),
):
    r = _load_inspection(db, rid)
    if r.status != "draft":
        raise BizException(R.SAFETY_INVALID_STATE, "已提交的巡检记录不能删除")
    recycle.soft_delete(db, SafetyInspection, r, user=current, module="safety", resource="SafetyInspection")
    audit(
        db, user_id=current.id, module="safety", action="inspection_delete",
        biz_type="safety_inspection", biz_id=r.id, detail={"recordNo": r.record_no},
    )
    db.commit()
    return {"id": rid}


@router.post("/inspections/{rid}/submit")
def submit_inspection(
    rid: int,
    current: User = Depends(require_perm("safety:inspection:submit")),
    db: Session = Depends(get_db),
):
    """提交巡检记录：异常项自动生成隐患（待整改），返回生成的隐患 id。"""
    r = _load_inspection(db, rid)
    hazard_ids = svc.submit_inspection(db, r, current)
    audit(
        db, user_id=current.id, module="safety", action="inspection_submit",
        biz_type="safety_inspection", biz_id=r.id,
        detail={"recordNo": r.record_no, "result": r.result, "hazards": len(hazard_ids)},
    )
    db.commit()
    return {"record": _out_inspection(r), "hazards": hazard_ids}


@router.post("/inspections/{rid}/close")
def close_inspection(
    rid: int,
    current: User = Depends(require_perm("safety:inspection:submit")),
    db: Session = Depends(get_db),
):
    """巡检记录闭环：关联隐患必须全部关闭。"""
    r = _load_inspection(db, rid)
    svc.close_inspection(db, r)
    audit(
        db, user_id=current.id, module="safety", action="inspection_close",
        biz_type="safety_inspection", biz_id=r.id, detail={"recordNo": r.record_no},
    )
    db.commit()
    return _out_inspection(r)


# ---------------- 隐患整改 ----------------


@router.get("/hazards")
def list_hazards(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_any_perm("safety:inspection:list", "safety:hazard:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(SafetyHazard),
        SafetyHazard,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["hazard_no", "description", "responsible_name"],
        filter_cols={"status", "level", "source"},
        range_cols={"deadline", "found_at"},
        sort_cols={"id", "hazard_no", "level", "status", "deadline", "found_at", "create_time"},
        default_sort=("id", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_out_hazard(h) for h in rows], "total": total, "page": page, "size": size}


@router.get("/hazards/counts")
def hazard_counts(
    user: User = Depends(require_any_perm("safety:inspection:list", "safety:hazard:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(SafetyHazard.status, func.count())
        .where(SafetyHazard.deleted == 0)
        .group_by(SafetyHazard.status)
    ).all()
    data = {s: 0 for s in svc.HAZARD_STATUSES}
    data.update({s: n for s, n in rows})
    data["all"] = sum(data.values())
    all_hazards = db.scalars(select(SafetyHazard).where(SafetyHazard.deleted == 0)).all()
    data["overdue"] = sum(1 for h in all_hazards if svc.is_overdue(h))
    return data


@router.get("/hazards/{hid}")
def get_hazard(
    hid: int,
    user: User = Depends(require_any_perm("safety:inspection:list", "safety:hazard:list")),
    db: Session = Depends(get_db),
):
    return _out_hazard(_load_hazard(db, hid))


@router.post("/hazards", status_code=201)
def create_hazard(
    body: S.HazardIn,
    current: User = Depends(require_perm("safety:hazard:create")),
    db: Session = Depends(get_db),
):
    hazard_no = (body.hazard_no or "").strip() or svc.next_hazard_no(db)
    svc.ensure_no_available(db, SafetyHazard, "hazard_no", hazard_no, "隐患编号")
    h = SafetyHazard(
        hazard_no=hazard_no,
        inspection_id=body.inspection_id,
        record_no=body.record_no,
        source=body.source,
        description=body.description,
        level=body.level,
        status=body.status,
        responsible_id=body.responsible_id,
        responsible_name=body.responsible_name,
        deadline=body.deadline,
        found_at=body.found_at or datetime.now(),
        measure=body.measure,
        remark=body.remark,
    )
    db.add(h)
    db.flush()
    audit(
        db, user_id=current.id, module="safety", action="hazard_create",
        biz_type="safety_hazard", biz_id=h.id,
        detail={"hazardNo": h.hazard_no, "level": h.level, "source": h.source},
    )
    db.commit()
    return _out_hazard(h)


@router.put("/hazards/{hid}")
def update_hazard(
    hid: int,
    body: S.HazardIn,
    current: User = Depends(require_perm("safety:hazard:create")),
    db: Session = Depends(get_db),
):
    h = _load_hazard(db, hid)
    if h.status == "closed":
        raise BizException(R.SAFETY_INVALID_STATE, "已关闭的隐患不能修改")
    hazard_no = (body.hazard_no or "").strip()
    if hazard_no and hazard_no != h.hazard_no:
        svc.ensure_no_available(db, SafetyHazard, "hazard_no", hazard_no, "隐患编号")
        h.hazard_no = hazard_no
    h.description = body.description
    h.level = body.level
    h.status = body.status
    h.responsible_id = body.responsible_id
    h.responsible_name = body.responsible_name
    h.deadline = body.deadline
    h.measure = body.measure or h.measure
    h.remark = body.remark
    audit(
        db, user_id=current.id, module="safety", action="hazard_update",
        biz_type="safety_hazard", biz_id=h.id, detail={"hazardNo": h.hazard_no},
    )
    db.commit()
    return _out_hazard(h)


@router.post("/hazards/{hid}/rectify")
def rectify_hazard(
    hid: int,
    body: S.RectifyIn,
    current: User = Depends(require_perm("safety:hazard:rectify")),
    db: Session = Depends(get_db),
):
    """隐患整改（措施必填）：登记整改 → 待验证。"""
    h = _load_hazard(db, hid)
    svc.rectify_hazard(db, h, body.measure, current)
    audit(
        db, user_id=current.id, module="safety", action="hazard_rectify",
        biz_type="safety_hazard", biz_id=h.id,
        detail={"hazardNo": h.hazard_no, "status": h.status, "measure": h.measure},
    )
    db.commit()
    return _out_hazard(h)


@router.post("/hazards/{hid}/verify")
def verify_hazard(
    hid: int,
    body: S.VerifyIn,
    current: User = Depends(require_perm("safety:hazard:verify")),
    db: Session = Depends(get_db),
):
    """隐患验证：通过 → 已关闭；不通过 → 退回整改中。"""
    h = _load_hazard(db, hid)
    svc.verify_hazard(db, h, body.verify_result, body.pass_, current)
    audit(
        db, user_id=current.id, module="safety", action="hazard_verify",
        biz_type="safety_hazard", biz_id=h.id,
        detail={"hazardNo": h.hazard_no, "status": h.status, "pass": body.pass_},
    )
    db.commit()
    return _out_hazard(h)


# ---------------- 统计看板 ----------------


@router.get("/board")
def safety_board(
    user: User = Depends(require_any_perm("safety:inspection:list", "safety:hazard:list")),
    db: Session = Depends(get_db),
):
    return svc.board(db)
