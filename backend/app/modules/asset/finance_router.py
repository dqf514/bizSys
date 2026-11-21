"""资产财务路由：固定资产与折旧、处置与报废、工具领用归还。

与 `app.modules.asset.router` 同前缀 `/asset`，业务域同为 asset。
"""

from datetime import date, datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.common.filters import apply_list_filters
from app.common.pagination import PAGE_MAX, PageParams
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.asset import schemas as S
from app.modules.asset import service as svc
from app.modules.asset.models import Depreciation, Disposal, FixedAsset, Tool, ToolLoan
from app.modules.auth.models import User
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/asset", tags=["asset"], route_class=EnvelopeRoute)

ASSET_EXPORT_COLS = [
    {"key": "assetNo", "label": "资产编号", "width": 16},
    {"key": "name", "label": "资产名称", "width": 24},
    {"key": "categoryText", "label": "类别", "width": 12},
    {"key": "model", "label": "型号", "width": 16},
    {"key": "deptName", "label": "使用部门", "width": 18},
    {"key": "custodianName", "label": "使用人", "width": 12},
    {"key": "purchaseDate", "label": "购置日期", "width": 12},
    {"key": "originalValue", "label": "原值", "width": 14},
    {"key": "accumDepreciation", "label": "累计折旧", "width": 14},
    {"key": "netValue", "label": "净值", "width": 14},
    {"key": "statusText", "label": "状态", "width": 10},
]

DISPOSAL_EXPORT_COLS = [
    {"key": "disposalNo", "label": "处置单号", "width": 18},
    {"key": "assetNo", "label": "资产编号", "width": 16},
    {"key": "assetName", "label": "资产名称", "width": 24},
    {"key": "disposalTypeText", "label": "处置方式", "width": 12},
    {"key": "applyDate", "label": "申请日期", "width": 12},
    {"key": "originalValue", "label": "原值", "width": 14},
    {"key": "netValue", "label": "处置前净值", "width": 14},
    {"key": "disposalAmount", "label": "处置收入", "width": 14},
    {"key": "handlerName", "label": "经办人", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
]

TOOL_EXPORT_COLS = [
    {"key": "toolNo", "label": "工具编号", "width": 16},
    {"key": "name", "label": "工具名称", "width": 24},
    {"key": "spec", "label": "规格", "width": 20},
    {"key": "model", "label": "型号", "width": 16},
    {"key": "categoryText", "label": "类别", "width": 12},
    {"key": "warehouseName", "label": "存放仓库", "width": 16},
    {"key": "deptName", "label": "归属部门", "width": 18},
    {"key": "value", "label": "价值", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
]

TOOL_LOAN_EXPORT_COLS = [
    {"key": "loanNo", "label": "领用单号", "width": 18},
    {"key": "toolNo", "label": "工具编号", "width": 16},
    {"key": "toolName", "label": "工具名称", "width": 24},
    {"key": "borrowerName", "label": "领用人", "width": 12},
    {"key": "deptName", "label": "归属部门", "width": 18},
    {"key": "loanDate", "label": "领用日期", "width": 12},
    {"key": "dueDate", "label": "应归还", "width": 12},
    {"key": "returnDate", "label": "归还日期", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
]

STATUS_CN = {
    "in_use": "在用",
    "idle": "闲置",
    "repaired": "维修中",
    "scrapped": "已报废",
    "draft": "草稿",
    "approved": "已批准",
    "done": "已处置",
    "rejected": "已驳回",
    "in_stock": "在库",
    "loaned": "已借出",
    "maintenance": "维修中",
    "borrowed": "借出中",
    "returned": "已归还",
    "overdue": "已逾期",
}

CATEGORY_CN = {
    "equipment": "设备",
    "vehicle": "车辆",
    "furniture": "家具",
    "instrument": "仪器仪表",
    "software": "软件",
    "other": "其他",
}

DISPOSAL_TYPE_CN = {"scrap": "报废", "sell": "出售", "donate": "捐赠", "transfer": "调拨"}

METHOD_CN = {
    "straight_line": "平均年限法",
    "double_declining": "双倍余额递减法",
    "sum_of_years": "年数总和法",
}


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
    rows = db.execute(
        select(model.status, func.count()).where(model.deleted == 0).group_by(model.status)
    ).all()
    data = {k: 0 for k in keys}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


def _load_asset(db: Session, asset_id: int) -> FixedAsset:
    asset = db.get(FixedAsset, asset_id)
    if not asset or asset.deleted:
        raise BizException(R.ASSET_ITEM_NOT_FOUND, "固定资产不存在")
    return asset


# ---------------- 固定资产 ----------------


def _asset_out(a: FixedAsset) -> dict:
    return {
        "id": a.id,
        "assetNo": a.asset_no,
        "name": a.name,
        "category": a.category or "",
        "categoryText": _text(CATEGORY_CN, a.category),
        "model": a.model or "",
        "spec": a.spec or "",
        "deptId": a.dept_id,
        "deptName": a.dept_name or "",
        "custodianId": a.custodian_id,
        "custodianName": a.custodian_name or "",
        "location": a.location or "",
        "purchaseDate": _d(a.purchase_date),
        "originalValue": _n(a.original_value),
        "salvageRate": float(a.salvage_rate or 0),
        "usefulLifeMonths": a.useful_life_months,
        "accumDepreciation": float(a.accum_depreciation or 0),
        "netValue": svc.asset_net_value(a),
        "remark": a.remark or "",
        "status": a.status,
        "statusText": _text(STATUS_CN, a.status),
        "version": a.version,
        "createTime": _t(a.create_time),
        "updateTime": _t(a.update_time),
    }


def _asset_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(FixedAsset),
        FixedAsset,
        request.query_params,
        db,
        page,
        search_cols=["asset_no", "name", "model", "spec", "custodian_name", "location"],
        filter_cols={"status", "category", "dept_id", "custodian_id"},
        range_cols={"purchase_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "asset_no", "name", "original_value", "status"},
    )


@router.get("/assets")
def list_assets(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:asset:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _asset_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_asset_out(a) for a in rows], "total": total, "page": page, "size": size}


@router.get("/assets/counts")
def asset_counts(
    user: User = Depends(require_perm("asset:asset:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, FixedAsset, ("in_use", "idle", "repaired", "scrapped"))


@router.get("/assets/{aid}")
def get_asset(
    aid: int,
    user: User = Depends(require_perm("asset:asset:list")),
    db: Session = Depends(get_db),
):
    a = _load_asset(db, aid)
    data = _asset_out(a)
    data["depreciations"] = [_depreciation_out(d) for d in svc.depreciation_rows(db, aid)]
    disposals = db.scalars(
        select(Disposal).where(Disposal.asset_id == aid, Disposal.deleted == 0).order_by(Disposal.id.desc())
    ).all()
    data["disposals"] = [_disposal_out(d) for d in disposals]
    return data


@router.post("/assets", status_code=201)
def create_asset(
    body: S.FixedAssetIn,
    current: User = Depends(require_perm("asset:asset:create")),
    db: Session = Depends(get_db),
):
    dup = db.scalar(select(FixedAsset.id).where(FixedAsset.asset_no == body.asset_no, FixedAsset.deleted == 0))
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "资产编号已存在")
    a = FixedAsset(
        asset_no=body.asset_no,
        name=body.name,
        category=body.category,
        model=body.model,
        spec=body.spec,
        dept_id=body.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id) or (current.dept_name or ""),
        custodian_id=body.custodian_id,
        custodian_name=body.custodian_name,
        location=body.location,
        purchase_date=body.purchase_date,
        original_value=body.original_value,
        salvage_rate=body.salvage_rate,
        useful_life_months=body.useful_life_months,
        accum_depreciation=0,
        net_value=body.original_value,
        remark=body.remark,
        status=body.status,
        create_by=current.id,
    )
    db.add(a)
    db.flush()
    # 净值口径与 _asset_out 一致：原值 - 累计折旧 - 残值
    a.net_value = svc.asset_net_value(a)
    audit(
        db, user_id=current.id, module="asset", action="asset_create",
        biz_type="fixed_asset", biz_id=a.id, detail={"assetNo": a.asset_no},
    )
    db.commit()
    return _asset_out(a)


@router.put("/assets/{aid}")
def update_asset(
    aid: int,
    body: S.FixedAssetIn,
    current: User = Depends(require_perm("asset:asset:edit")),
    db: Session = Depends(get_db),
):
    a = _load_asset(db, aid)
    svc.check_version(a, body.version)
    dup = db.scalar(
        select(FixedAsset.id).where(
            FixedAsset.asset_no == body.asset_no, FixedAsset.id != aid, FixedAsset.deleted == 0
        )
    )
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "资产编号已存在")
    a.asset_no = body.asset_no
    a.name = body.name
    a.category = body.category
    a.model = body.model
    a.spec = body.spec
    a.dept_id = body.dept_id
    a.dept_name = svc.load_dept_name(db, body.dept_id) or a.dept_name
    a.custodian_id = body.custodian_id
    a.custodian_name = body.custodian_name
    a.location = body.location
    a.purchase_date = body.purchase_date
    a.original_value = body.original_value
    a.salvage_rate = body.salvage_rate
    a.useful_life_months = body.useful_life_months
    a.remark = body.remark
    a.status = body.status
    a.net_value = svc.asset_net_value(a)
    a.version += 1
    a.update_by = current.id
    a.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="asset_update",
        biz_type="fixed_asset", biz_id=aid, detail={"assetNo": a.asset_no},
    )
    db.commit()
    return _asset_out(a)


@router.delete("/assets/{aid}")
def delete_asset(
    aid: int,
    current: User = Depends(require_perm("asset:asset:delete")),
    db: Session = Depends(get_db),
):
    a = _load_asset(db, aid)
    open_disposal = db.scalar(
        select(Disposal.id).where(
            Disposal.asset_id == aid, Disposal.status.in_(("draft", "approved")), Disposal.deleted == 0
        )
    )
    if open_disposal:
        raise BizException(R.ASSET_INVALID_STATE, "该资产存在未完结的处置单，不能删除")
    a.deleted = 1
    a.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="asset_delete",
        biz_type="fixed_asset", biz_id=aid, detail={"assetNo": a.asset_no},
    )
    db.commit()
    return None


@router.post("/assets/export")
def export_assets(
    request: Request,
    current: User = Depends(require_perm("asset:asset:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _asset_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = [_asset_out(a) for a in db.scalars(stmt).all()]
    payload = export_xlsx_styled(rows, ASSET_EXPORT_COLS, "fixed_assets")
    audit(
        db, user_id=current.id, module="asset", action="asset_export",
        detail={"count": len(rows)}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('fixed_assets')}"},
    )


# ---------------- 折旧 ----------------


def _depreciation_out(d: Depreciation) -> dict:
    return {
        "id": d.id,
        "assetId": d.asset_id,
        "assetNo": d.asset_no or "",
        "assetName": d.asset_name or "",
        "period": d.period,
        "amount": float(d.amount or 0),
        "accumAmount": float(d.accum_amount or 0),
        "netValue": float(d.net_value or 0),
        "method": d.method or "",
        "methodText": _text(METHOD_CN, d.method),
        "operatorId": d.operator_id,
        "operatorName": d.operator_name or "",
        "happenAt": _t(d.happen_at),
        "remark": d.remark or "",
        "version": d.version,
        "createTime": _t(d.create_time),
    }


@router.get("/depreciations")
def list_depreciations(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:depreciation:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(Depreciation),
        Depreciation,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["asset_no", "asset_name", "period"],
        filter_cols={"asset_id", "method"},
        range_cols={"period", "create_time"},
        sort_cols={"update_time", "create_time", "id", "period", "amount"},
        default_sort=("period", "desc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_depreciation_out(d) for d in rows], "total": total, "page": page, "size": size}


@router.get("/depreciations/{did}")
def get_depreciation(
    did: int,
    user: User = Depends(require_perm("asset:depreciation:list")),
    db: Session = Depends(get_db),
):
    d = db.get(Depreciation, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _depreciation_out(d)


@router.post("/assets/{aid}/depreciate")
def depreciate_asset(
    aid: int,
    body: S.DepreciateIn,
    current: User = Depends(require_perm("asset:depreciation:create")),
    db: Session = Depends(get_db),
):
    """按期计提折旧：写入折旧记录并回写资产累计折旧与净值。"""
    a = _load_asset(db, aid)
    if a.status == "scrapped":
        raise BizException(R.ASSET_INVALID_STATE, "已报废资产不能计提折旧")
    exists = db.scalar(
        select(Depreciation.id).where(
            Depreciation.asset_id == aid, Depreciation.period == body.period, Depreciation.deleted == 0
        )
    )
    if exists:
        raise BizException(R.ASSET_INVALID_STATE, f"{body.period} 期折旧已计提，不能重复计提")
    amount = svc.depreciation_amount(a, body.method, body.period)
    accum = round(float(a.accum_depreciation or 0) + amount, 2)
    net = svc.asset_net_value(a) if amount == 0 else round(
        max(float(a.original_value or 0) - accum - float(a.original_value or 0) * float(a.salvage_rate or 0), 0.0),
        2,
    )
    row = Depreciation(
        asset_id=aid,
        asset_no=a.asset_no,
        asset_name=a.name,
        period=body.period,
        amount=amount,
        accum_amount=accum,
        net_value=net,
        method=body.method,
        operator_id=current.id,
        operator_name=current.name or current.username,
        happen_at=datetime.now(),
        remark=body.remark,
        create_by=current.id,
    )
    db.add(row)
    a.accum_depreciation = accum
    a.net_value = net
    a.version += 1
    a.update_by = current.id
    a.update_time = datetime.now()
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="asset_depreciate",
        biz_type="depreciation", biz_id=row.id,
        detail={"assetNo": a.asset_no, "period": body.period, "amount": amount},
    )
    db.commit()
    return _depreciation_out(row)


@router.post("/depreciations", status_code=201)
def create_depreciation(
    body: S.DepreciationIn,
    current: User = Depends(require_perm("asset:depreciation:create")),
    db: Session = Depends(get_db),
):
    """手工登记折旧记录（补录历史期间）。"""
    a = _load_asset(db, body.asset_id)
    exists = db.scalar(
        select(Depreciation.id).where(
            Depreciation.asset_id == body.asset_id, Depreciation.period == body.period, Depreciation.deleted == 0
        )
    )
    if exists:
        raise BizException(R.ASSET_INVALID_STATE, f"{body.period} 期折旧已登记")
    accum = round(float(a.accum_depreciation or 0) + float(body.amount), 2)
    salvage = float(a.original_value or 0) * float(a.salvage_rate or 0)
    net = round(max(float(a.original_value or 0) - accum - salvage, 0.0), 2)
    row = Depreciation(
        asset_id=body.asset_id,
        asset_no=a.asset_no,
        asset_name=a.name,
        period=body.period,
        amount=body.amount,
        accum_amount=accum,
        net_value=net,
        method=body.method,
        operator_id=current.id,
        operator_name=current.name or current.username,
        happen_at=datetime.now(),
        remark=body.remark,
        create_by=current.id,
    )
    db.add(row)
    a.accum_depreciation = accum
    a.net_value = net
    a.version += 1
    a.update_by = current.id
    a.update_time = datetime.now()
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="depreciation_create",
        biz_type="depreciation", biz_id=row.id, detail={"assetNo": a.asset_no, "period": body.period},
    )
    db.commit()
    return _depreciation_out(row)


@router.put("/depreciations/{did}")
def update_depreciation(
    did: int,
    body: S.DepreciationIn,
    current: User = Depends(require_perm("asset:depreciation:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(Depreciation, did)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_version(row, body.version)
    a = _load_asset(db, body.asset_id)
    dup = db.scalar(
        select(Depreciation.id).where(
            Depreciation.asset_id == body.asset_id,
            Depreciation.period == body.period,
            Depreciation.id != did,
            Depreciation.deleted == 0,
        )
    )
    if dup:
        raise BizException(R.ASSET_INVALID_STATE, f"{body.period} 期折旧已登记")
    old = float(row.amount or 0)
    accum = round(float(a.accum_depreciation or 0) - old + float(body.amount), 2)
    salvage = float(a.original_value or 0) * float(a.salvage_rate or 0)
    net = round(max(float(a.original_value or 0) - accum - salvage, 0.0), 2)
    row.asset_id = body.asset_id
    row.asset_no = a.asset_no
    row.asset_name = a.name
    row.period = body.period
    row.amount = body.amount
    row.accum_amount = accum
    row.net_value = net
    row.method = body.method
    row.remark = body.remark
    row.version += 1
    row.update_by = current.id
    row.update_time = datetime.now()
    a.accum_depreciation = accum
    a.net_value = net
    a.version += 1
    a.update_by = current.id
    a.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="depreciation_update",
        biz_type="depreciation", biz_id=did,
    )
    db.commit()
    return _depreciation_out(row)


@router.delete("/depreciations/{did}")
def delete_depreciation(
    did: int,
    current: User = Depends(require_perm("asset:depreciation:delete")),
    db: Session = Depends(get_db),
):
    row = db.get(Depreciation, did)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    a = db.get(FixedAsset, row.asset_id)
    if a and not a.deleted:
        accum = round(max(float(a.accum_depreciation or 0) - float(row.amount or 0), 0.0), 2)
        a.accum_depreciation = accum
        a.net_value = svc.asset_net_value(a)
        a.version += 1
        a.update_by = current.id
        a.update_time = datetime.now()
    row.deleted = 1
    row.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="depreciation_delete",
        biz_type="depreciation", biz_id=did,
    )
    db.commit()
    return None


# ---------------- 处置与报废 ----------------


def _disposal_out(d: Disposal) -> dict:
    return {
        "id": d.id,
        "disposalNo": d.disposal_no,
        "assetId": d.asset_id,
        "assetNo": d.asset_no or "",
        "assetName": d.asset_name or "",
        "disposalType": d.disposal_type or "",
        "disposalTypeText": _text(DISPOSAL_TYPE_CN, d.disposal_type),
        "applyDate": _d(d.apply_date),
        "originalValue": _n(d.original_value),
        "netValue": _n(d.net_value),
        "disposalAmount": _n(d.disposal_amount),
        "reason": d.reason or "",
        "handlerId": d.handler_id,
        "handlerName": d.handler_name or "",
        "approverId": d.approver_id,
        "approverName": d.approver_name or "",
        "approveAt": _t(d.approve_at),
        "remark": d.remark or "",
        "status": d.status,
        "statusText": _text(STATUS_CN, d.status),
        "version": d.version,
        "createTime": _t(d.create_time),
        "updateTime": _t(d.update_time),
    }


def _disposal_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(Disposal),
        Disposal,
        request.query_params,
        db,
        page,
        search_cols=["disposal_no", "asset_no", "asset_name", "reason"],
        filter_cols={"status", "asset_id", "disposal_type"},
        range_cols={"apply_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "disposal_no", "apply_date", "status"},
    )


@router.get("/disposals")
def list_disposals(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:disposal:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _disposal_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_disposal_out(d) for d in rows], "total": total, "page": page, "size": size}


@router.get("/disposals/counts")
def disposal_counts(
    user: User = Depends(require_perm("asset:disposal:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, Disposal, ("draft", "approved", "done", "rejected"))


@router.get("/disposals/{did}")
def get_disposal(
    did: int,
    user: User = Depends(require_perm("asset:disposal:list")),
    db: Session = Depends(get_db),
):
    d = db.get(Disposal, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _disposal_out(d)


@router.post("/disposals", status_code=201)
def create_disposal(
    body: S.DisposalIn,
    current: User = Depends(require_perm("asset:disposal:create")),
    db: Session = Depends(get_db),
):
    a = _load_asset(db, body.asset_id)
    if a.status == "scrapped":
        raise BizException(R.ASSET_INVALID_STATE, "该资产已报废，不能重复申请处置")
    open_one = db.scalar(
        select(Disposal.id).where(
            Disposal.asset_id == body.asset_id,
            Disposal.status.in_(("draft", "approved")),
            Disposal.deleted == 0,
        )
    )
    if open_one:
        raise BizException(R.ASSET_INVALID_STATE, "该资产存在未完结的处置单")
    d = Disposal(
        disposal_no=svc.next_asset_no(db, "asset_disposal"),
        asset_id=a.id,
        asset_no=a.asset_no,
        asset_name=a.name,
        disposal_type=body.disposal_type,
        apply_date=body.apply_date or date.today(),
        original_value=a.original_value,
        net_value=svc.asset_net_value(a),
        disposal_amount=body.disposal_amount,
        reason=body.reason,
        handler_id=body.handler_id or current.id,
        handler_name=body.handler_name or (current.name or current.username),
        remark=body.remark,
        status="draft",
        create_by=current.id,
    )
    db.add(d)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="disposal_create",
        biz_type="disposal", biz_id=d.id, detail={"assetNo": a.asset_no},
    )
    db.commit()
    return _disposal_out(d)


@router.put("/disposals/{did}")
def update_disposal(
    did: int,
    body: S.DisposalIn,
    current: User = Depends(require_perm("asset:disposal:edit")),
    db: Session = Depends(get_db),
):
    d = db.get(Disposal, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(d.status, ("draft",), "已批准的处置单只读，不能编辑")
    svc.check_version(d, body.version)
    a = _load_asset(db, body.asset_id)
    d.asset_id = a.id
    d.asset_no = a.asset_no
    d.asset_name = a.name
    d.disposal_type = body.disposal_type
    d.apply_date = body.apply_date or d.apply_date
    d.original_value = a.original_value
    d.net_value = svc.asset_net_value(a)
    d.disposal_amount = body.disposal_amount
    d.reason = body.reason
    d.handler_id = body.handler_id or d.handler_id
    d.handler_name = body.handler_name or d.handler_name
    d.remark = body.remark
    d.version += 1
    d.update_by = current.id
    d.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="disposal_update",
        biz_type="disposal", biz_id=did,
    )
    db.commit()
    return _disposal_out(d)


@router.delete("/disposals/{did}")
def delete_disposal(
    did: int,
    current: User = Depends(require_perm("asset:disposal:delete")),
    db: Session = Depends(get_db),
):
    d = db.get(Disposal, did)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(d.status, ("draft", "rejected"), "已批准的处置单不能删除")
    d.deleted = 1
    d.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="disposal_delete",
        biz_type="disposal", biz_id=did,
    )
    db.commit()
    return None


@router.post("/disposals/{did}/approve")
def approve_disposal(
    did: int,
    current: User = Depends(require_perm("asset:disposal:approve")),
    db: Session = Depends(get_db),
):
    d = db.get(Disposal, did, with_for_update=True)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(d.status, ("draft",), "仅草稿处置单可批准")
    d.status = "approved"
    d.approver_id = current.id
    d.approver_name = current.name or current.username
    d.approve_at = datetime.now()
    d.version += 1
    d.update_by = current.id
    d.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="disposal_approve",
        biz_type="disposal", biz_id=did, detail={"disposalNo": d.disposal_no},
    )
    db.commit()
    return _disposal_out(d)


@router.post("/disposals/{did}/complete")
def complete_disposal(
    did: int,
    current: User = Depends(require_perm("asset:disposal:complete")),
    db: Session = Depends(get_db),
):
    """处置完成：资产状态置为已报废（调拨除外）。"""
    d = db.get(Disposal, did, with_for_update=True)
    if not d or d.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(d.status, ("approved",), "仅已批准处置单可完成处置")
    d.status = "done"
    d.version += 1
    d.update_by = current.id
    d.update_time = datetime.now()
    a = db.get(FixedAsset, d.asset_id)
    if a and not a.deleted:
        a.status = "idle" if d.disposal_type == "transfer" else "scrapped"
        a.version += 1
        a.update_by = current.id
        a.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="disposal_complete",
        biz_type="disposal", biz_id=did, detail={"disposalNo": d.disposal_no},
    )
    db.commit()
    return _disposal_out(d)


@router.post("/disposals/export")
def export_disposals(
    request: Request,
    current: User = Depends(require_perm("asset:disposal:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _disposal_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = [_disposal_out(d) for d in db.scalars(stmt).all()]
    payload = export_xlsx_styled(rows, DISPOSAL_EXPORT_COLS, "asset_disposals")
    audit(
        db, user_id=current.id, module="asset", action="disposal_export",
        detail={"count": len(rows)}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_disposals')}"},
    )


# ---------------- 工具台账 ----------------


def _tool_out(t: Tool) -> dict:
    return {
        "id": t.id,
        "toolNo": t.tool_no,
        "name": t.name,
        "spec": t.spec or "",
        "model": t.model or "",
        "category": t.category or "",
        "categoryText": _text(CATEGORY_CN, t.category),
        "unit": t.unit or "",
        "warehouseId": t.warehouse_id,
        "warehouseName": t.warehouse_name or "",
        "deptId": t.dept_id,
        "deptName": t.dept_name or "",
        "purchaseDate": _d(t.purchase_date),
        "value": _n(t.value),
        "remark": t.remark or "",
        "status": t.status,
        "statusText": _text(STATUS_CN, t.status),
        "version": t.version,
        "createTime": _t(t.create_time),
        "updateTime": _t(t.update_time),
    }


def _tool_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(Tool),
        Tool,
        request.query_params,
        db,
        page,
        search_cols=["tool_no", "name", "spec", "model"],
        filter_cols={"status", "category", "warehouse_id", "dept_id"},
        range_cols={"purchase_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "tool_no", "name", "value", "status"},
    )


@router.get("/tools")
def list_tools(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:tool:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _tool_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_tool_out(t) for t in rows], "total": total, "page": page, "size": size}


@router.get("/tools/counts")
def tool_counts(
    user: User = Depends(require_perm("asset:tool:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, Tool, ("in_stock", "loaned", "maintenance", "scrapped"))


@router.get("/tools/all")
def list_all_tools(
    user: User = Depends(require_perm("asset:tool:list")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(Tool).where(Tool.deleted == 0).order_by(Tool.tool_no)).all()
    return [
        {"id": t.id, "toolNo": t.tool_no, "name": t.name, "spec": t.spec or "", "status": t.status}
        for t in rows
    ]


@router.get("/tools/{tid}")
def get_tool(
    tid: int,
    user: User = Depends(require_perm("asset:tool:list")),
    db: Session = Depends(get_db),
):
    t = db.get(Tool, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _tool_out(t)
    loans = db.scalars(
        select(ToolLoan).where(ToolLoan.tool_id == tid, ToolLoan.deleted == 0).order_by(ToolLoan.id.desc())
    ).all()
    data["loans"] = [_tool_loan_out(loan) for loan in loans]
    return data


@router.post("/tools", status_code=201)
def create_tool(
    body: S.ToolIn,
    current: User = Depends(require_perm("asset:tool:create")),
    db: Session = Depends(get_db),
):
    dup = db.scalar(select(Tool.id).where(Tool.tool_no == body.tool_no, Tool.deleted == 0))
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "工具编号已存在")
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    t = Tool(
        tool_no=body.tool_no,
        name=body.name,
        spec=body.spec,
        model=body.model,
        category=body.category,
        unit=body.unit,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        dept_id=body.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id) or (current.dept_name or ""),
        purchase_date=body.purchase_date,
        value=body.value,
        remark=body.remark,
        status=body.status,
        create_by=current.id,
    )
    db.add(t)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="tool_create",
        biz_type="tool", biz_id=t.id, detail={"toolNo": t.tool_no},
    )
    db.commit()
    return _tool_out(t)


@router.put("/tools/{tid}")
def update_tool(
    tid: int,
    body: S.ToolIn,
    current: User = Depends(require_perm("asset:tool:edit")),
    db: Session = Depends(get_db),
):
    t = db.get(Tool, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_version(t, body.version)
    dup = db.scalar(select(Tool.id).where(Tool.tool_no == body.tool_no, Tool.id != tid, Tool.deleted == 0))
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "工具编号已存在")
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    t.tool_no = body.tool_no
    t.name = body.name
    t.spec = body.spec
    t.model = body.model
    t.category = body.category
    t.unit = body.unit
    t.warehouse_id = warehouse_id
    t.warehouse_name = warehouse_name
    t.dept_id = body.dept_id
    t.dept_name = svc.load_dept_name(db, body.dept_id) or t.dept_name
    t.purchase_date = body.purchase_date
    t.value = body.value
    t.remark = body.remark
    t.status = body.status
    t.version += 1
    t.update_by = current.id
    t.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="tool_update",
        biz_type="tool", biz_id=tid,
    )
    db.commit()
    return _tool_out(t)


@router.delete("/tools/{tid}")
def delete_tool(
    tid: int,
    current: User = Depends(require_perm("asset:tool:delete")),
    db: Session = Depends(get_db),
):
    t = db.get(Tool, tid)
    if not t or t.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if svc.open_tool_loan(db, tid):
        raise BizException(R.ASSET_INVALID_STATE, "该工具尚有未归还的领用记录")
    t.deleted = 1
    t.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="tool_delete",
        biz_type="tool", biz_id=tid,
    )
    db.commit()
    return None


@router.post("/tools/export")
def export_tools(
    request: Request,
    current: User = Depends(require_perm("asset:tool:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _tool_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = [_tool_out(t) for t in db.scalars(stmt).all()]
    payload = export_xlsx_styled(rows, TOOL_EXPORT_COLS, "asset_tools")
    audit(
        db, user_id=current.id, module="asset", action="tool_export",
        detail={"count": len(rows)}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_tools')}"},
    )


# ---------------- 工具领用归还 ----------------


def _tool_loan_out(loan: ToolLoan) -> dict:
    state = svc.loan_status_text(loan.status, loan.due_date)
    return {
        "id": loan.id,
        "loanNo": loan.loan_no,
        "toolId": loan.tool_id,
        "toolNo": loan.tool_no or "",
        "toolName": loan.tool_name or "",
        "borrowerId": loan.borrower_id,
        "borrowerName": loan.borrower_name or "",
        "deptId": loan.dept_id,
        "deptName": loan.dept_name or "",
        "loanDate": _d(loan.loan_date),
        "dueDate": _d(loan.due_date),
        "returnDate": _d(loan.return_date),
        "purpose": loan.purpose or "",
        "remark": loan.remark or "",
        "status": loan.status,
        "statusText": _text(STATUS_CN, state),
        "version": loan.version,
        "createTime": _t(loan.create_time),
        "updateTime": _t(loan.update_time),
    }


def _tool_loan_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(ToolLoan),
        ToolLoan,
        request.query_params,
        db,
        page,
        search_cols=["loan_no", "tool_no", "tool_name", "borrower_name"],
        filter_cols={"status", "tool_id", "borrower_id", "dept_id"},
        range_cols={"loan_date", "due_date", "return_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "loan_no", "loan_date", "due_date", "status"},
    )


@router.get("/tool-loans")
def list_tool_loans(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:toolLoan:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _tool_loan_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_tool_loan_out(loan) for loan in rows], "total": total, "page": page, "size": size}


@router.get("/tool-loans/counts")
def tool_loan_counts(
    user: User = Depends(require_perm("asset:toolLoan:list")),
    db: Session = Depends(get_db),
):
    data = _counts(db, ToolLoan, ("borrowed", "returned"))
    overdue = db.scalar(
        select(func.count())
        .select_from(ToolLoan)
        .where(ToolLoan.deleted == 0, ToolLoan.status == "borrowed", ToolLoan.due_date < date.today())
    ) or 0
    data["overdue"] = int(overdue)
    return data


@router.get("/tool-loans/{lid}")
def get_tool_loan(
    lid: int,
    user: User = Depends(require_perm("asset:toolLoan:list")),
    db: Session = Depends(get_db),
):
    loan = db.get(ToolLoan, lid)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _tool_loan_out(loan)


@router.post("/tool-loans", status_code=201)
def create_tool_loan(
    body: S.ToolLoanIn,
    current: User = Depends(require_perm("asset:toolLoan:create")),
    db: Session = Depends(get_db),
):
    _, tool_no, tool_name = svc.load_tool(db, body.tool_id)
    if svc.open_tool_loan(db, body.tool_id):
        raise BizException(R.ASSET_LOAN_NOT_RETURNED, "该工具尚未归还，不能再次领用")
    t = db.get(Tool, body.tool_id)
    loan = ToolLoan(
        loan_no=svc.next_asset_no(db, "asset_tool_loan"),
        tool_id=body.tool_id,
        tool_no=tool_no,
        tool_name=tool_name,
        borrower_id=body.borrower_id or current.id,
        borrower_name=body.borrower_name or (current.name or current.username),
        dept_id=body.dept_id or current.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id) or (current.dept_name or ""),
        loan_date=body.loan_date or date.today(),
        due_date=body.due_date,
        purpose=body.purpose,
        remark=body.remark,
        status="borrowed",
        create_by=current.id,
    )
    db.add(loan)
    if t and t.status == "in_stock":
        t.status = "loaned"
        t.update_time = datetime.now()
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="tool_loan_create",
        biz_type="tool_loan", biz_id=loan.id, detail={"toolNo": tool_no},
    )
    db.commit()
    return _tool_loan_out(loan)


@router.put("/tool-loans/{lid}")
def update_tool_loan(
    lid: int,
    body: S.ToolLoanIn,
    current: User = Depends(require_perm("asset:toolLoan:edit")),
    db: Session = Depends(get_db),
):
    loan = db.get(ToolLoan, lid)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(loan.status, ("borrowed",), "已归还记录只读，不能编辑")
    svc.check_version(loan, body.version)
    _, tool_no, tool_name = svc.load_tool(db, body.tool_id)
    loan.tool_id = body.tool_id
    loan.tool_no = tool_no
    loan.tool_name = tool_name
    loan.borrower_id = body.borrower_id or loan.borrower_id
    loan.borrower_name = body.borrower_name or loan.borrower_name
    loan.dept_id = body.dept_id or loan.dept_id
    loan.dept_name = svc.load_dept_name(db, body.dept_id) or loan.dept_name
    loan.loan_date = body.loan_date or loan.loan_date
    loan.due_date = body.due_date
    loan.purpose = body.purpose
    loan.remark = body.remark
    loan.version += 1
    loan.update_by = current.id
    loan.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="tool_loan_update",
        biz_type="tool_loan", biz_id=lid,
    )
    db.commit()
    return _tool_loan_out(loan)


@router.delete("/tool-loans/{lid}")
def delete_tool_loan(
    lid: int,
    current: User = Depends(require_perm("asset:toolLoan:delete")),
    db: Session = Depends(get_db),
):
    loan = db.get(ToolLoan, lid)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(loan.status, ("borrowed",), "已归还记录不能删除")
    t = db.get(Tool, loan.tool_id)
    if t and t.status == "loaned" and not svc.open_tool_loan(db, loan.tool_id):
        t.status = "in_stock"
        t.update_time = datetime.now()
    loan.deleted = 1
    loan.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="tool_loan_delete",
        biz_type="tool_loan", biz_id=lid,
    )
    db.commit()
    return None


@router.post("/tool-loans/{lid}/return")
def return_tool_loan(
    lid: int,
    body: S.LoanReturnIn | None = None,
    current: User = Depends(require_perm("asset:toolLoan:return")),
    db: Session = Depends(get_db),
):
    loan = db.get(ToolLoan, lid, with_for_update=True)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(loan.status, ("borrowed",), "该领用单已归还")
    loan.return_date = body.return_date if body and body.return_date else date.today()
    if body and body.remark:
        loan.remark = body.remark
    loan.status = "returned"
    loan.version += 1
    loan.update_by = current.id
    loan.update_time = datetime.now()
    t = db.get(Tool, loan.tool_id)
    if t and t.status == "loaned":
        t.status = "in_stock"
        t.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="tool_loan_return",
        biz_type="tool_loan", biz_id=lid, detail={"loanNo": loan.loan_no},
    )
    db.commit()
    return _tool_loan_out(loan)


@router.post("/tool-loans/export")
def export_tool_loans(
    request: Request,
    current: User = Depends(require_perm("asset:toolLoan:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _tool_loan_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    rows = [_tool_loan_out(loan) for loan in db.scalars(stmt).all()]
    payload = export_xlsx_styled(rows, TOOL_LOAN_EXPORT_COLS, "asset_tool_loans")
    audit(
        db, user_id=current.id, module="asset", action="tool_loan_export",
        detail={"count": len(rows)}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_tool_loans')}"},
    )
