"""资产模块路由（仓储与库存部分）/api/v1/asset。

覆盖：仓库与库位、存货档案、采购订单、到货验收、库存台账、库存盘点、样车样件台账、样件出借归还。
统一框架：部门 → sys_dept；供应公司 → crm_customer；权限 → sys_menu（module:resource:action）。
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
from app.modules.asset.models import (
    Item,
    Location,
    Prototype,
    PrototypeLoan,
    PurchaseOrder,
    PurchaseOrderItem,
    Receipt,
    ReceiptItem,
    StockCount,
    StockCountItem,
    StockLedger,
    Warehouse,
)
from app.modules.auth.models import User
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/asset", tags=["asset"], route_class=EnvelopeRoute)

WAREHOUSE_EXPORT_COLS = [
    {"key": "code", "label": "仓库编码", "width": 14},
    {"key": "name", "label": "仓库名称", "width": 24},
    {"key": "deptName", "label": "归属部门", "width": 18},
    {"key": "address", "label": "地址", "width": 32},
    {"key": "managerName", "label": "负责人", "width": 12},
    {"key": "locationCount", "label": "库位数", "width": 10},
    {"key": "qtyOnHand", "label": "在库数量", "width": 12},
    {"key": "stockAmount", "label": "库存金额", "width": 14},
    {"key": "statusText", "label": "状态", "width": 10},
]

ITEM_EXPORT_COLS = [
    {"key": "code", "label": "存货编码", "width": 16},
    {"key": "name", "label": "存货名称", "width": 26},
    {"key": "spec", "label": "规格型号", "width": 20},
    {"key": "unit", "label": "单位", "width": 8},
    {"key": "categoryText", "label": "类别", "width": 12},
    {"key": "unitPrice", "label": "单价", "width": 12},
    {"key": "qtyOnHand", "label": "现存数量", "width": 12},
    {"key": "safetyStock", "label": "安全库存", "width": 12},
    {"key": "supplierName", "label": "供应公司", "width": 24},
    {"key": "statusText", "label": "状态", "width": 10},
]

PO_EXPORT_COLS = [
    {"key": "orderNo", "label": "订单编号", "width": 18},
    {"key": "title", "label": "订单标题", "width": 28},
    {"key": "supplierName", "label": "供应公司", "width": 24},
    {"key": "orderDate", "label": "下单日期", "width": 12},
    {"key": "arriveDate", "label": "预计到货", "width": 12},
    {"key": "totalAmount", "label": "订单金额", "width": 14},
    {"key": "statusText", "label": "状态", "width": 10},
    {"key": "createTime", "label": "创建时间", "width": 19},
]

RECEIPT_EXPORT_COLS = [
    {"key": "receiptNo", "label": "验收单号", "width": 18},
    {"key": "orderNo", "label": "来源订单", "width": 18},
    {"key": "warehouseName", "label": "入库仓库", "width": 18},
    {"key": "supplierName", "label": "供应公司", "width": 24},
    {"key": "arriveDate", "label": "到货日期", "width": 12},
    {"key": "totalQty", "label": "到货数量", "width": 12},
    {"key": "qualifiedQty", "label": "合格数量", "width": 12},
    {"key": "inspectorName", "label": "验收人", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
]

LEDGER_EXPORT_COLS = [
    {"key": "happenAt", "label": "发生时间", "width": 19},
    {"key": "directionText", "label": "方向", "width": 8},
    {"key": "itemCode", "label": "存货编码", "width": 16},
    {"key": "itemName", "label": "存货名称", "width": 26},
    {"key": "warehouseName", "label": "仓库", "width": 16},
    {"key": "locationCode", "label": "库位", "width": 14},
    {"key": "quantity", "label": "数量", "width": 10},
    {"key": "amount", "label": "金额", "width": 12},
    {"key": "reasonText", "label": "原因", "width": 12},
    {"key": "bizNo", "label": "来源单号", "width": 18},
    {"key": "operatorName", "label": "操作人", "width": 12},
]

COUNT_EXPORT_COLS = [
    {"key": "countNo", "label": "盘点单号", "width": 18},
    {"key": "warehouseName", "label": "仓库", "width": 18},
    {"key": "countDate", "label": "盘点日期", "width": 12},
    {"key": "totalQty", "label": "盘点条目", "width": 12},
    {"key": "diffCount", "label": "差异条目", "width": 12},
    {"key": "operatorName", "label": "盘点人", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
]

PROTOTYPE_EXPORT_COLS = [
    {"key": "code", "label": "样件编号", "width": 18},
    {"key": "name", "label": "样件名称", "width": 24},
    {"key": "kindText", "label": "类型", "width": 12},
    {"key": "model", "label": "型号", "width": 16},
    {"key": "vin", "label": "识别号", "width": 18},
    {"key": "deptName", "label": "归属部门", "width": 18},
    {"key": "locationName", "label": "存放位置", "width": 18},
    {"key": "value", "label": "价值", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
]

PROTOTYPE_LOAN_EXPORT_COLS = [
    {"key": "loanNo", "label": "借出单号", "width": 18},
    {"key": "prototypeCode", "label": "样件编号", "width": 18},
    {"key": "prototypeName", "label": "样件名称", "width": 24},
    {"key": "borrowerName", "label": "借用人", "width": 12},
    {"key": "deptName", "label": "归属部门", "width": 18},
    {"key": "loanDate", "label": "借出日期", "width": 12},
    {"key": "dueDate", "label": "应归还", "width": 12},
    {"key": "returnDate", "label": "归还日期", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
]

STATUS_CN = {
    "enabled": "启用",
    "disabled": "停用",
    "draft": "草稿",
    "confirmed": "已确认",
    "closed": "已完成",
    "accepted": "合格",
    "partial": "部分合格",
    "rejected": "不合格",
    "counting": "盘点中",
    "finished": "已盘点",
    "in": "入库",
    "out": "出库",
    "borrowed": "借出中",
    "returned": "已归还",
    "overdue": "已逾期",
    "in_stock": "在库",
    "loaned": "已借出",
    "maintenance": "维修中",
    "scrapped": "已报废",
}

CATEGORY_CN = {
    "raw": "原材料",
    "spare": "备品备件",
    "consumable": "耗材",
    "packing": "包装材料",
    "other": "其他",
}

KIND_CN = {"vehicle": "样车", "part": "样件", "prototype": "样机", "other": "其他"}

REASON_CN = {
    "purchase": "采购入库",
    "receipt": "验收入库",
    "count": "盘点调整",
    "borrow": "领用出库",
    "return": "归还入库",
    "scrap": "报废出库",
    "manual": "手工登记",
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


# ---------------- 仓库与库位 ----------------


def _warehouse_out(db: Session, w: Warehouse) -> dict:
    loc_count = db.scalar(
        select(func.count()).select_from(Location).where(
            Location.warehouse_id == w.id, Location.deleted == 0
        )
    ) or 0
    qty = db.scalar(
        select(func.coalesce(func.sum(StockLedger.quantity), 0)).where(
            StockLedger.warehouse_id == w.id, StockLedger.deleted == 0, StockLedger.direction == "in"
        )
    )
    out_qty = db.scalar(
        select(func.coalesce(func.sum(StockLedger.quantity), 0)).where(
            StockLedger.warehouse_id == w.id, StockLedger.deleted == 0, StockLedger.direction == "out"
        )
    )
    qty_on_hand = round(float(qty or 0) - float(out_qty or 0), 2)
    amount = db.scalar(
        select(func.coalesce(func.sum(StockLedger.amount), 0)).where(
            StockLedger.warehouse_id == w.id,
            StockLedger.deleted == 0,
            StockLedger.direction == "in",
        )
    )
    out_amount = db.scalar(
        select(func.coalesce(func.sum(StockLedger.amount), 0)).where(
            StockLedger.warehouse_id == w.id,
            StockLedger.deleted == 0,
            StockLedger.direction == "out",
        )
    )
    stock_amount = round(float(amount or 0) - float(out_amount or 0), 2)
    return {
        "id": w.id,
        "code": w.code,
        "name": w.name,
        "deptId": w.dept_id,
        "deptName": w.dept_name,
        "address": w.address or "",
        "managerId": w.manager_id,
        "managerName": w.manager_name,
        "capacity": w.capacity,
        "locationCount": int(loc_count),
        "qtyOnHand": qty_on_hand,
        "stockAmount": stock_amount,
        "phone": w.phone or "",
        "remark": w.remark or "",
        "status": w.status,
        "statusText": _text(STATUS_CN, w.status),
        "version": w.version,
        "createTime": _t(w.create_time),
        "updateTime": _t(w.update_time),
    }


def _location_out(loc: Location) -> dict:
    return {
        "id": loc.id,
        "warehouseId": loc.warehouse_id,
        "code": loc.code,
        "name": loc.name or "",
        "area": loc.area or "",
        "capacity": _n(loc.capacity),
        "used": float(loc.used or 0),
        "qtyOnHand": float(loc.qty_on_hand or 0),
        "remark": loc.remark or "",
        "status": loc.status,
        "statusText": _text(STATUS_CN, loc.status),
        "version": loc.version,
        "createTime": _t(loc.create_time),
        "updateTime": _t(loc.update_time),
    }


@router.get("/warehouses")
def list_warehouses(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:warehouse:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(Warehouse),
        Warehouse,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["code", "name", "address", "manager_name"],
        filter_cols={"status", "dept_id"},
        sort_cols={"update_time", "create_time", "id", "code", "name", "status"},
        default_sort=("code", "asc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_warehouse_out(db, w) for w in rows], "total": total, "page": page, "size": size}


@router.get("/warehouses/counts")
def warehouse_counts(
    user: User = Depends(require_perm("asset:warehouse:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, Warehouse, ("enabled", "disabled"))


@router.get("/warehouses/stats")
def warehouse_stats(
    user: User = Depends(require_perm("asset:warehouse:list")),
    db: Session = Depends(get_db),
):
    """页头统计卡：仓库数 / 库位数 / 在库批次 / 库存金额。"""
    warehouse_count = db.scalar(
        select(func.count()).select_from(Warehouse).where(Warehouse.deleted == 0)
    ) or 0
    location_count = db.scalar(
        select(func.count()).select_from(Location).where(Location.deleted == 0)
    ) or 0
    rows = db.execute(
        select(StockLedger.item_id, StockLedger.location_id, StockLedger.direction, func.sum(StockLedger.quantity))
        .where(StockLedger.deleted == 0)
        .group_by(StockLedger.item_id, StockLedger.location_id, StockLedger.direction)
    ).all()
    batches: dict[tuple, float] = {}
    for item_id, location_id, direction, qty in rows:
        key = (item_id, location_id)
        batches[key] = batches.get(key, 0.0) + (float(qty) if direction == "in" else -float(qty))
    batch_count = sum(1 for v in batches.values() if v > 0)
    stock_map = svc.item_stock_map(db, [k[0] for k in batches if k[0]])
    amount_rows = db.execute(
        select(StockLedger.item_id, StockLedger.direction, func.sum(StockLedger.amount))
        .where(StockLedger.deleted == 0)
        .group_by(StockLedger.item_id, StockLedger.direction)
    ).all()
    stock_amount = 0.0
    for _item_id, direction, amount in amount_rows:
        stock_amount += float(amount or 0) if direction == "in" else -float(amount or 0)
    return {
        "warehouseCount": int(warehouse_count),
        "locationCount": int(location_count),
        "batchCount": batch_count,
        "stockAmount": round(stock_amount, 2),
        "stockMap": {str(k): v for k, v in stock_map.items()},
    }


@router.get("/warehouses/{wid}")
def get_warehouse(
    wid: int,
    user: User = Depends(require_perm("asset:warehouse:list")),
    db: Session = Depends(get_db),
):
    w = db.get(Warehouse, wid)
    if not w or w.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _warehouse_out(db, w)
    locations = db.scalars(
        select(Location).where(Location.warehouse_id == wid, Location.deleted == 0).order_by(Location.code)
    ).all()
    data["locations"] = [_location_out(loc) for loc in locations]
    return data


@router.post("/warehouses", status_code=201)
def create_warehouse(
    body: S.WarehouseIn,
    current: User = Depends(require_perm("asset:warehouse:create")),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(Warehouse.id).where(Warehouse.code == body.code, Warehouse.deleted == 0))
    if exists:
        raise BizException(R.ASSET_CODE_DUPLICATE, "仓库编码已存在")
    w = Warehouse(
        code=body.code,
        name=body.name,
        dept_id=body.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id),
        address=body.address,
        manager_id=body.manager_id,
        manager_name=body.manager_name or (current.name or current.username),
        capacity=body.capacity,
        phone=body.phone,
        remark=body.remark,
        status=body.status,
        create_by=current.id,
    )
    db.add(w)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="warehouse_create",
        biz_type="warehouse", biz_id=w.id,
    )
    db.commit()
    return _warehouse_out(db, w)


@router.put("/warehouses/{wid}")
def update_warehouse(
    wid: int,
    body: S.WarehouseIn,
    current: User = Depends(require_perm("asset:warehouse:edit")),
    db: Session = Depends(get_db),
):
    w = db.get(Warehouse, wid)
    if not w or w.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_version(w, body.version)
    dup = db.scalar(
        select(Warehouse.id).where(Warehouse.code == body.code, Warehouse.id != wid, Warehouse.deleted == 0)
    )
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "仓库编码已存在")
    w.code = body.code
    w.name = body.name
    w.dept_id = body.dept_id
    w.dept_name = svc.load_dept_name(db, body.dept_id)
    w.address = body.address
    w.manager_id = body.manager_id
    w.manager_name = body.manager_name or w.manager_name
    w.capacity = body.capacity
    w.phone = body.phone
    w.remark = body.remark
    w.status = body.status
    w.version += 1
    w.update_by = current.id
    w.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="warehouse_update",
        biz_type="warehouse", biz_id=wid,
    )
    db.commit()
    return _warehouse_out(db, w)


@router.delete("/warehouses/{wid}")
def delete_warehouse(
    wid: int,
    current: User = Depends(require_perm("asset:warehouse:delete")),
    db: Session = Depends(get_db),
):
    w = db.get(Warehouse, wid)
    if not w or w.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    loc_count = db.scalar(
        select(func.count()).select_from(Location).where(
            Location.warehouse_id == wid, Location.deleted == 0
        )
    ) or 0
    if loc_count:
        raise BizException(R.ASSET_INVALID_STATE, "仓库下仍有库位，请先删除库位")
    w.deleted = 1
    w.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="warehouse_delete",
        biz_type="warehouse", biz_id=wid,
    )
    db.commit()
    return None


@router.post("/warehouses/export")
def export_warehouses(
    request: Request,
    current: User = Depends(require_perm("asset:warehouse:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = apply_list_filters(
        select(Warehouse),
        Warehouse,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=["code", "name", "address", "manager_name"],
        filter_cols={"status", "dept_id"},
        sort_cols={"update_time", "create_time", "id", "code", "name", "status"},
        default_sort=("code", "asc"),
    )
    rows = [_warehouse_out(db, w) for w in db.scalars(stmt).all()]
    payload = export_xlsx_styled(rows, WAREHOUSE_EXPORT_COLS, "warehouses")
    audit(
        db, user_id=current.id, module="asset", action="warehouse_export",
        detail={"count": len(rows)}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('warehouses')}"},
    )


@router.get("/locations")
def list_locations(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:warehouse:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(Location),
        Location,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["code", "name", "area"],
        filter_cols={"status", "warehouse_id", "area"},
        sort_cols={"update_time", "create_time", "id", "code", "area"},
        default_sort=("code", "asc"),
    )
    rows = db.scalars(stmt).all()
    return {"items": [_location_out(loc) for loc in rows], "total": total, "page": page, "size": size}


@router.get("/locations/all")
def list_all_locations(
    user: User = Depends(require_perm("asset:warehouse:list")),
    db: Session = Depends(get_db),
):
    """下拉选用的库位全集（不分页）。"""
    rows = db.scalars(
        select(Location).where(Location.deleted == 0).order_by(Location.warehouse_id, Location.code)
    ).all()
    wh_names = {
        w.id: w.name
        for w in db.scalars(select(Warehouse).where(Warehouse.deleted == 0)).all()
    }
    return [
        {
            "id": loc.id,
            "warehouseId": loc.warehouse_id,
            "warehouseName": wh_names.get(loc.warehouse_id, ""),
            "code": loc.code,
            "name": loc.name or loc.code,
            "area": loc.area or "",
        }
        for loc in rows
    ]


@router.post("/locations", status_code=201)
def create_location(
    body: S.LocationIn,
    current: User = Depends(require_perm("asset:warehouse:create")),
    db: Session = Depends(get_db),
):
    warehouse_id, _ = svc.load_warehouse(db, body.warehouse_id)
    dup = db.scalar(
        select(Location.id).where(
            Location.warehouse_id == warehouse_id, Location.code == body.code, Location.deleted == 0
        )
    )
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "同一仓库下库位编码已存在")
    loc = Location(
        warehouse_id=warehouse_id,
        code=body.code,
        name=body.name,
        area=body.area,
        capacity=body.capacity,
        used=0,
        qty_on_hand=0,
        remark=body.remark,
        status=body.status,
        create_by=current.id,
    )
    db.add(loc)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="location_create",
        biz_type="location", biz_id=loc.id,
    )
    db.commit()
    return _location_out(loc)


@router.put("/locations/{lid}")
def update_location(
    lid: int,
    body: S.LocationIn,
    current: User = Depends(require_perm("asset:warehouse:edit")),
    db: Session = Depends(get_db),
):
    loc = db.get(Location, lid)
    if not loc or loc.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_version(loc, body.version)
    warehouse_id, _ = svc.load_warehouse(db, body.warehouse_id)
    dup = db.scalar(
        select(Location.id).where(
            Location.warehouse_id == warehouse_id,
            Location.code == body.code,
            Location.id != lid,
            Location.deleted == 0,
        )
    )
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "同一仓库下库位编码已存在")
    loc.warehouse_id = warehouse_id
    loc.code = body.code
    loc.name = body.name
    loc.area = body.area
    loc.capacity = body.capacity
    loc.remark = body.remark
    loc.status = body.status
    loc.version += 1
    loc.update_by = current.id
    loc.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="location_update",
        biz_type="location", biz_id=lid,
    )
    db.commit()
    return _location_out(loc)


@router.delete("/locations/{lid}")
def delete_location(
    lid: int,
    current: User = Depends(require_perm("asset:warehouse:delete")),
    db: Session = Depends(get_db),
):
    loc = db.get(Location, lid)
    if not loc or loc.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if float(loc.qty_on_hand or 0) != 0:
        raise BizException(R.ASSET_INVALID_STATE, "库位仍有在库数量，不能删除")
    loc.deleted = 1
    loc.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="location_delete",
        biz_type="location", biz_id=lid,
    )
    db.commit()
    return None


# ---------------- 存货档案 ----------------


def _item_out(item: Item, db: Session, stock: float | None = None) -> dict:
    qty = svc.item_stock(db, item.id) if stock is None else stock
    return {
        "id": item.id,
        "code": item.code,
        "name": item.name,
        "spec": item.spec or "",
        "unit": item.unit or "",
        "category": item.category or "",
        "categoryText": _text(CATEGORY_CN, item.category),
        "unitPrice": _n(item.unit_price),
        "safetyStock": float(item.safety_stock or 0),
        "maxStock": float(item.max_stock or 0),
        "defaultWarehouseId": item.default_warehouse_id,
        "defaultLocationId": item.default_location_id,
        "supplierId": item.supplier_id,
        "supplierName": item.supplier_name or "",
        "manufacturer": item.manufacturer or "",
        "deptId": item.dept_id,
        "deptName": item.dept_name or "",
        "qtyOnHand": qty,
        "lowStock": float(item.safety_stock or 0) > 0 and qty < float(item.safety_stock or 0),
        "remark": item.remark or "",
        "status": item.status,
        "statusText": _text(STATUS_CN, item.status),
        "version": item.version,
        "createTime": _t(item.create_time),
        "updateTime": _t(item.update_time),
    }


@router.get("/items")
def list_items(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:item:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(Item),
        Item,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["code", "name", "spec", "supplier_name", "manufacturer"],
        filter_cols={"status", "category", "supplier_id", "dept_id", "default_warehouse_id"},
        range_cols={"create_time"},
        sort_cols={"update_time", "create_time", "id", "code", "name", "unit_price", "status"},
    )
    rows = list(db.scalars(stmt).all())
    stock_map = svc.item_stock_map(db, [i.id for i in rows])
    items = [_item_out(i, db, stock_map.get(i.id, 0.0)) for i in rows]
    if (request.query_params.get("filters[low_stock]") or "") == "1":
        items = [i for i in items if i["lowStock"]]
        total = len(items)
    return {"items": items, "total": total, "page": page, "size": size}


@router.get("/items/counts")
def item_counts(
    user: User = Depends(require_perm("asset:item:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, Item, ("enabled", "disabled"))


@router.get("/items/all")
def list_all_items(
    user: User = Depends(require_perm("asset:item:list")),
    db: Session = Depends(get_db),
):
    """下拉选用的存货全集。"""
    rows = db.scalars(select(Item).where(Item.deleted == 0).order_by(Item.code)).all()
    return [
        {
            "id": i.id,
            "code": i.code,
            "name": i.name,
            "spec": i.spec or "",
            "unit": i.unit or "",
            "unitPrice": _n(i.unit_price),
        }
        for i in rows
    ]


@router.get("/items/{iid}")
def get_item(
    iid: int,
    user: User = Depends(require_perm("asset:item:list")),
    db: Session = Depends(get_db),
):
    item = db.get(Item, iid)
    if not item or item.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _item_out(item, db)


@router.post("/items", status_code=201)
def create_item(
    body: S.ItemIn,
    current: User = Depends(require_perm("asset:item:create")),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(Item.id).where(Item.code == body.code, Item.deleted == 0))
    if exists:
        raise BizException(R.ASSET_CODE_DUPLICATE, "存货编码已存在")
    supplier_name = svc.load_supplier_name(db, body.supplier_id)
    item = Item(
        code=body.code,
        name=body.name,
        spec=body.spec,
        unit=body.unit,
        category=body.category,
        unit_price=body.unit_price,
        safety_stock=body.safety_stock,
        max_stock=body.max_stock,
        default_warehouse_id=body.default_warehouse_id,
        default_location_id=body.default_location_id,
        supplier_id=body.supplier_id,
        supplier_name=supplier_name,
        manufacturer=body.manufacturer,
        dept_id=body.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id),
        remark=body.remark,
        status=body.status,
        create_by=current.id,
    )
    db.add(item)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="item_create",
        biz_type="item", biz_id=item.id,
    )
    db.commit()
    return _item_out(item, db)


@router.put("/items/{iid}")
def update_item(
    iid: int,
    body: S.ItemIn,
    current: User = Depends(require_perm("asset:item:edit")),
    db: Session = Depends(get_db),
):
    item = db.get(Item, iid)
    if not item or item.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_version(item, body.version)
    dup = db.scalar(select(Item.id).where(Item.code == body.code, Item.id != iid, Item.deleted == 0))
    if dup:
        raise BizException(R.ASSET_CODE_DUPLICATE, "存货编码已存在")
    item.code = body.code
    item.name = body.name
    item.spec = body.spec
    item.unit = body.unit
    item.category = body.category
    item.unit_price = body.unit_price
    item.safety_stock = body.safety_stock
    item.max_stock = body.max_stock
    item.default_warehouse_id = body.default_warehouse_id
    item.default_location_id = body.default_location_id
    item.supplier_id = body.supplier_id
    item.supplier_name = svc.load_supplier_name(db, body.supplier_id)
    item.manufacturer = body.manufacturer
    item.dept_id = body.dept_id
    item.dept_name = svc.load_dept_name(db, body.dept_id)
    item.remark = body.remark
    item.status = body.status
    item.version += 1
    item.update_by = current.id
    item.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="item_update",
        biz_type="item", biz_id=iid,
    )
    db.commit()
    return _item_out(item, db)


@router.delete("/items/{iid}")
def delete_item(
    iid: int,
    current: User = Depends(require_perm("asset:item:delete")),
    db: Session = Depends(get_db),
):
    item = db.get(Item, iid)
    if not item or item.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    stock = svc.item_stock(db, iid)
    if stock != 0:
        raise BizException(R.ASSET_INVALID_STATE, "该存货仍有库存，不能删除")
    item.deleted = 1
    item.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="item_delete",
        biz_type="item", biz_id=iid,
    )
    db.commit()
    return None


@router.post("/items/export")
def export_items(
    request: Request,
    current: User = Depends(require_perm("asset:item:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = apply_list_filters(
        select(Item),
        Item,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=["code", "name", "spec", "supplier_name", "manufacturer"],
        filter_cols={"status", "category", "supplier_id", "dept_id", "default_warehouse_id"},
        sort_cols={"update_time", "create_time", "id", "code", "name", "unit_price", "status"},
    )
    rows = list(db.scalars(stmt).all())
    stock_map = svc.item_stock_map(db, [i.id for i in rows])
    payload = export_xlsx_styled(
        [_item_out(i, db, stock_map.get(i.id, 0.0)) for i in rows], ITEM_EXPORT_COLS, "inventory_items"
    )
    audit(
        db, user_id=current.id, module="asset", action="item_export",
        detail={"count": len(rows)}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('inventory_items')}"},
    )


# ---------------- 采购订单 ----------------


def _po_out(po: PurchaseOrder) -> dict:
    return {
        "id": po.id,
        "orderNo": po.order_no,
        "title": po.title,
        "supplierId": po.supplier_id,
        "supplierName": po.supplier_name or "",
        "deptId": po.dept_id,
        "deptName": po.dept_name or "",
        "orderDate": _d(po.order_date),
        "arriveDate": _d(po.arrive_date),
        "totalAmount": _n(po.total_amount),
        "handlerId": po.handler_id,
        "handlerName": po.handler_name or "",
        "remark": po.remark or "",
        "status": po.status,
        "statusText": _text(STATUS_CN, po.status),
        "items": [
            {
                "id": i.id,
                "itemId": i.item_id,
                "itemCode": i.item_code or "",
                "itemName": i.item_name,
                "spec": i.spec or "",
                "unit": i.unit or "",
                "quantity": float(i.quantity or 0),
                "price": _n(i.price),
                "remark": i.remark or "",
            }
            for i in (po.items or [])
            if not i.deleted
        ],
        "version": po.version,
        "createTime": _t(po.create_time),
        "updateTime": _t(po.update_time),
    }


def _po_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(PurchaseOrder),
        PurchaseOrder,
        request.query_params,
        db,
        page,
        search_cols=["order_no", "title", "supplier_name"],
        filter_cols={"status", "supplier_id", "dept_id"},
        range_cols={"order_date", "arrive_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "order_no", "total_amount", "order_date", "status"},
    )


@router.get("/purchase-orders")
def list_purchase_orders(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:purchaseOrder:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _po_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_po_out(po) for po in rows], "total": total, "page": page, "size": size}


@router.get("/purchase-orders/counts")
def purchase_order_counts(
    user: User = Depends(require_perm("asset:purchaseOrder:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, PurchaseOrder, ("draft", "confirmed", "closed"))


@router.get("/purchase-orders/{pid}")
def get_purchase_order(
    pid: int,
    user: User = Depends(require_perm("asset:purchaseOrder:list")),
    db: Session = Depends(get_db),
):
    po = db.get(PurchaseOrder, pid)
    if not po or po.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _po_out(po)
    receipts = db.scalars(
        select(Receipt).where(Receipt.order_id == pid, Receipt.deleted == 0).order_by(Receipt.id.desc())
    ).all()
    data["receipts"] = [
        {"id": r.id, "receiptNo": r.receipt_no, "status": r.status, "statusText": _text(STATUS_CN, r.status)}
        for r in receipts
    ]
    return data


@router.post("/purchase-orders", status_code=201)
def create_purchase_order(
    body: S.PurchaseOrderIn,
    current: User = Depends(require_perm("asset:purchaseOrder:create")),
    db: Session = Depends(get_db),
):
    supplier_name = svc.load_supplier_name(db, body.supplier_id)
    po = PurchaseOrder(
        order_no=svc.next_asset_no(db, "asset_purchase_order"),
        title=body.title,
        supplier_id=body.supplier_id,
        supplier_name=supplier_name,
        dept_id=body.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id) or (current.dept_name or ""),
        order_date=body.order_date or date.today(),
        arrive_date=body.arrive_date,
        total_amount=body.total_amount,
        handler_id=body.handler_id or current.id,
        handler_name=body.handler_name or (current.name or current.username),
        remark=body.remark,
        status="draft",
        create_by=current.id,
    )
    for it in body.items:
        item_id, item_code, item_name, unit, price = svc.load_item(db, it.item_id)
        po.items.append(
            PurchaseOrderItem(
                item_id=item_id,
                item_code=item_code or it.item_code,
                item_name=it.item_name,
                spec=it.spec,
                unit=unit or it.unit,
                quantity=it.quantity,
                price=it.price if it.price is not None else price,
                remark=it.remark,
            )
        )
    db.add(po)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="purchase_order_create",
        biz_type="purchase_order", biz_id=po.id,
    )
    db.commit()
    return _po_out(po)


@router.put("/purchase-orders/{pid}")
def update_purchase_order(
    pid: int,
    body: S.PurchaseOrderIn,
    current: User = Depends(require_perm("asset:purchaseOrder:edit")),
    db: Session = Depends(get_db),
):
    po = db.get(PurchaseOrder, pid)
    if not po or po.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(po.status, ("draft",), "仅草稿订单可编辑")
    svc.check_version(po, body.version)
    supplier_name = svc.load_supplier_name(db, body.supplier_id)
    po.title = body.title
    po.supplier_id = body.supplier_id
    po.supplier_name = supplier_name
    po.dept_id = body.dept_id
    po.dept_name = svc.load_dept_name(db, body.dept_id) or po.dept_name
    po.order_date = body.order_date or po.order_date
    po.arrive_date = body.arrive_date
    po.total_amount = body.total_amount
    po.handler_id = body.handler_id or po.handler_id
    po.handler_name = body.handler_name or po.handler_name
    po.remark = body.remark
    po.items = []
    for it in body.items:
        item_id, item_code, item_name, unit, price = svc.load_item(db, it.item_id)
        po.items.append(
            PurchaseOrderItem(
                item_id=item_id,
                item_code=item_code or it.item_code,
                item_name=it.item_name,
                spec=it.spec,
                unit=unit or it.unit,
                quantity=it.quantity,
                price=it.price if it.price is not None else price,
                remark=it.remark,
            )
        )
    po.version += 1
    po.update_by = current.id
    po.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="purchase_order_update",
        biz_type="purchase_order", biz_id=pid,
    )
    db.commit()
    return _po_out(po)


@router.delete("/purchase-orders/{pid}")
def delete_purchase_order(
    pid: int,
    current: User = Depends(require_perm("asset:purchaseOrder:delete")),
    db: Session = Depends(get_db),
):
    po = db.get(PurchaseOrder, pid)
    if not po or po.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(po.status, ("draft",), "仅草稿订单可删除")
    po.deleted = 1
    po.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="purchase_order_delete",
        biz_type="purchase_order", biz_id=pid,
    )
    db.commit()
    return None


@router.post("/purchase-orders/{pid}/confirm")
def confirm_purchase_order(
    pid: int,
    current: User = Depends(require_perm("asset:purchaseOrder:confirm")),
    db: Session = Depends(get_db),
):
    po = db.get(PurchaseOrder, pid, with_for_update=True)
    if not po or po.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(po.status, ("draft",), "仅草稿订单可确认")
    po.status = "confirmed"
    po.version += 1
    po.update_by = current.id
    po.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="purchase_order_confirm",
        biz_type="purchase_order", biz_id=pid, detail={"orderNo": po.order_no},
    )
    db.commit()
    return _po_out(po)


@router.post("/purchase-orders/{pid}/close")
def close_purchase_order(
    pid: int,
    current: User = Depends(require_perm("asset:purchaseOrder:close")),
    db: Session = Depends(get_db),
):
    po = db.get(PurchaseOrder, pid, with_for_update=True)
    if not po or po.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(po.status, ("confirmed",), "仅已确认订单可关闭")
    po.status = "closed"
    po.version += 1
    po.update_by = current.id
    po.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="purchase_order_close",
        biz_type="purchase_order", biz_id=pid, detail={"orderNo": po.order_no},
    )
    db.commit()
    return _po_out(po)


@router.post("/purchase-orders/export")
def export_purchase_orders(
    request: Request,
    current: User = Depends(require_perm("asset:purchaseOrder:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _po_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    payload = export_xlsx_styled(
        [_po_out(po) for po in db.scalars(stmt).all()], PO_EXPORT_COLS, "asset_purchase_orders"
    )
    audit(
        db, user_id=current.id, module="asset", action="purchase_order_export",
        detail={"count": payload is not None}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_purchase_orders')}"
        },
    )


# ---------------- 到货验收 ----------------


def _receipt_out(r: Receipt) -> dict:
    return {
        "id": r.id,
        "receiptNo": r.receipt_no,
        "orderId": r.order_id,
        "orderNo": r.order_no or "",
        "warehouseId": r.warehouse_id,
        "warehouseName": r.warehouse_name or "",
        "supplierId": r.supplier_id,
        "supplierName": r.supplier_name or "",
        "arriveDate": _d(r.arrive_date),
        "totalQty": float(r.total_qty or 0),
        "qualifiedQty": float(r.qualified_qty or 0),
        "inspectorId": r.inspector_id,
        "inspectorName": r.inspector_name or "",
        "remark": r.remark or "",
        "status": r.status,
        "statusText": _text(STATUS_CN, r.status),
        "items": [
            {
                "id": i.id,
                "itemId": i.item_id,
                "itemCode": i.item_code or "",
                "itemName": i.item_name,
                "spec": i.spec or "",
                "unit": i.unit or "",
                "quantity": float(i.quantity or 0),
                "qualifiedQty": float(i.qualified_qty or 0),
                "locationId": i.location_id,
                "locationCode": i.location_code or "",
                "price": _n(i.price),
                "remark": i.remark or "",
            }
            for i in (r.items or [])
            if not i.deleted
        ],
        "version": r.version,
        "createTime": _t(r.create_time),
        "updateTime": _t(r.update_time),
    }


def _receipt_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(Receipt),
        Receipt,
        request.query_params,
        db,
        page,
        search_cols=["receipt_no", "order_no", "supplier_name", "warehouse_name"],
        filter_cols={"status", "order_id", "warehouse_id", "supplier_id"},
        range_cols={"arrive_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "receipt_no", "arrive_date", "status"},
    )


@router.get("/receipts")
def list_receipts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:receipt:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _receipt_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_receipt_out(r) for r in rows], "total": total, "page": page, "size": size}


@router.get("/receipts/counts")
def receipt_counts(
    user: User = Depends(require_perm("asset:receipt:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, Receipt, ("draft", "accepted", "partial", "rejected"))


@router.get("/receipts/{rid}")
def get_receipt(
    rid: int,
    user: User = Depends(require_perm("asset:receipt:list")),
    db: Session = Depends(get_db),
):
    r = db.get(Receipt, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _receipt_out(r)


@router.post("/receipts", status_code=201)
def create_receipt(
    body: S.ReceiptIn,
    current: User = Depends(require_perm("asset:receipt:create")),
    db: Session = Depends(get_db),
):
    order_no = ""
    order_status = ""
    if body.order_id:
        po = db.get(PurchaseOrder, body.order_id)
        if not po or po.deleted:
            raise BizException(R.GENERIC_NOT_FOUND, "来源采购订单不存在")
        if po.status == "draft":
            raise BizException(R.ASSET_INVALID_STATE, "采购订单尚未确认，不能验收")
        order_no = po.order_no
        order_status = po.status
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    supplier_name = svc.load_supplier_name(db, body.supplier_id)
    r = Receipt(
        receipt_no=svc.next_asset_no(db, "asset_receipt"),
        order_id=body.order_id,
        order_no=order_no,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        supplier_id=body.supplier_id,
        supplier_name=supplier_name,
        arrive_date=body.arrive_date or date.today(),
        total_qty=sum(i.quantity for i in body.items),
        qualified_qty=sum(i.qualified_qty for i in body.items),
        inspector_id=body.inspector_id or current.id,
        inspector_name=body.inspector_name or (current.name or current.username),
        remark=body.remark,
        status="draft",
        create_by=current.id,
    )
    for it in body.items:
        item_id, item_code, item_name, unit, price = svc.load_item(db, it.item_id)
        loc_id, loc_code, _, _ = svc.load_location(db, it.location_id)
        r.items.append(
            ReceiptItem(
                item_id=item_id,
                item_code=item_code or it.item_code,
                item_name=it.item_name,
                spec=it.spec,
                unit=unit or it.unit,
                quantity=it.quantity,
                qualified_qty=it.qualified_qty,
                location_id=loc_id,
                location_code=loc_code,
                price=it.price if it.price is not None else price,
                remark=it.remark,
            )
        )
    db.add(r)
    db.flush()
    if order_status == "confirmed":
        po.status = "closed"
        po.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="receipt_create",
        biz_type="receipt", biz_id=r.id,
    )
    db.commit()
    return _receipt_out(r)


@router.put("/receipts/{rid}")
def update_receipt(
    rid: int,
    body: S.ReceiptIn,
    current: User = Depends(require_perm("asset:receipt:edit")),
    db: Session = Depends(get_db),
):
    r = db.get(Receipt, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(r.status, ("draft",), "已验收单据只读，不能编辑")
    svc.check_version(r, body.version)
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    r.order_id = body.order_id
    r.warehouse_id = warehouse_id
    r.warehouse_name = warehouse_name
    r.supplier_id = body.supplier_id
    r.supplier_name = svc.load_supplier_name(db, body.supplier_id)
    r.arrive_date = body.arrive_date or r.arrive_date
    r.total_qty = sum(i.quantity for i in body.items)
    r.qualified_qty = sum(i.qualified_qty for i in body.items)
    r.inspector_id = body.inspector_id or r.inspector_id
    r.inspector_name = body.inspector_name or r.inspector_name
    r.remark = body.remark
    r.items = []
    for it in body.items:
        item_id, item_code, item_name, unit, price = svc.load_item(db, it.item_id)
        loc_id, loc_code, _, _ = svc.load_location(db, it.location_id)
        r.items.append(
            ReceiptItem(
                item_id=item_id,
                item_code=item_code or it.item_code,
                item_name=it.item_name,
                spec=it.spec,
                unit=unit or it.unit,
                quantity=it.quantity,
                qualified_qty=it.qualified_qty,
                location_id=loc_id,
                location_code=loc_code,
                price=it.price if it.price is not None else price,
                remark=it.remark,
            )
        )
    r.version += 1
    r.update_by = current.id
    r.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="receipt_update",
        biz_type="receipt", biz_id=rid,
    )
    db.commit()
    return _receipt_out(r)


@router.delete("/receipts/{rid}")
def delete_receipt(
    rid: int,
    current: User = Depends(require_perm("asset:receipt:delete")),
    db: Session = Depends(get_db),
):
    r = db.get(Receipt, rid)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(r.status, ("draft",), "已验收单据不能删除")
    r.deleted = 1
    r.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="receipt_delete",
        biz_type="receipt", biz_id=rid,
    )
    db.commit()
    return None


@router.post("/receipts/{rid}/accept")
def accept_receipt(
    rid: int,
    current: User = Depends(require_perm("asset:receipt:accept")),
    db: Session = Depends(get_db),
):
    """验收确认：合格数量写入库存台账并回写库位在库数量。"""
    r = db.get(Receipt, rid, with_for_update=True)
    if not r or r.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(r.status, ("draft",), "仅草稿验收单可确认")
    total = 0.0
    qualified = 0.0
    for line in [i for i in (r.items or []) if not i.deleted]:
        total += float(line.quantity or 0)
        qualified += float(line.qualified_qty or 0)
        if float(line.qualified_qty or 0) <= 0:
            continue
        svc.write_ledger(
            db,
            direction="in",
            item_id=line.item_id,
            item_code=line.item_code or "",
            item_name=line.item_name,
            unit=line.unit or "",
            quantity=float(line.qualified_qty),
            warehouse_id=r.warehouse_id,
            warehouse_name=r.warehouse_name,
            location_id=line.location_id,
            location_code=line.location_code or "",
            unit_price=_n(line.price),
            reason="receipt",
            biz_type="receipt",
            biz_id=r.id,
            biz_no=r.receipt_no,
            operator_id=current.id,
            operator_name=current.name or current.username,
            dept_id=current.dept_id,
            dept_name=current.dept_name or "",
            remark=line.remark or "",
        )
    r.total_qty = total
    r.qualified_qty = qualified
    if total <= 0:
        r.status = "rejected"
    elif qualified >= total:
        r.status = "accepted"
    elif qualified > 0:
        r.status = "partial"
    else:
        r.status = "rejected"
    r.version += 1
    r.update_by = current.id
    r.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="receipt_accept",
        biz_type="receipt", biz_id=rid, detail={"receiptNo": r.receipt_no, "status": r.status},
    )
    db.commit()
    return _receipt_out(r)


@router.post("/receipts/export")
def export_receipts(
    request: Request,
    current: User = Depends(require_perm("asset:receipt:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _receipt_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    payload = export_xlsx_styled(
        [_receipt_out(r) for r in db.scalars(stmt).all()], RECEIPT_EXPORT_COLS, "asset_receipts"
    )
    audit(
        db, user_id=current.id, module="asset", action="receipt_export",
        detail={"count": 1}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_receipts')}"},
    )


# ---------------- 库存台账 ----------------


def _ledger_out(row: StockLedger) -> dict:
    return {
        "id": row.id,
        "direction": row.direction,
        "directionText": _text(STATUS_CN, row.direction),
        "itemId": row.item_id,
        "itemCode": row.item_code or "",
        "itemName": row.item_name or "",
        "unit": row.unit or "",
        "warehouseId": row.warehouse_id,
        "warehouseName": row.warehouse_name or "",
        "locationId": row.location_id,
        "locationCode": row.location_code or "",
        "quantity": float(row.quantity or 0),
        "unitPrice": _n(row.unit_price),
        "amount": _n(row.amount),
        "reason": row.reason or "",
        "reasonText": _text(REASON_CN, row.reason),
        "bizType": row.biz_type or "",
        "bizId": row.biz_id,
        "bizNo": row.biz_no or "",
        "operatorId": row.operator_id,
        "operatorName": row.operator_name or "",
        "deptId": row.dept_id,
        "deptName": row.dept_name or "",
        "happenAt": _t(row.happen_at),
        "remark": row.remark or "",
        "editable": (row.biz_type or "manual") == "manual",
        "version": row.version,
        "createTime": _t(row.create_time),
    }


def _ledger_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(StockLedger),
        StockLedger,
        request.query_params,
        db,
        page,
        search_cols=["item_code", "item_name", "biz_no", "location_code", "warehouse_name"],
        filter_cols={"direction", "item_id", "warehouse_id", "location_id", "reason", "biz_type", "dept_id"},
        range_cols={"happen_at", "create_time"},
        sort_cols={"update_time", "create_time", "id", "happen_at", "quantity", "amount"},
        default_sort=("happen_at", "desc"),
    )


@router.get("/ledger")
def list_ledger(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:ledger:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _ledger_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_ledger_out(r) for r in rows], "total": total, "page": page, "size": size}


@router.get("/ledger/counts")
def ledger_counts(
    user: User = Depends(require_perm("asset:ledger:list")),
    db: Session = Depends(get_db),
):
    """方向计数：in / out / all。"""
    rows = db.execute(
        select(StockLedger.direction, func.count())
        .where(StockLedger.deleted == 0)
        .group_by(StockLedger.direction)
    ).all()
    data = {"in": 0, "out": 0}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = data["in"] + data["out"]
    return data


@router.get("/ledger/{lid}")
def get_ledger_row(
    lid: int,
    user: User = Depends(require_perm("asset:ledger:list")),
    db: Session = Depends(get_db),
):
    row = db.get(StockLedger, lid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _ledger_out(row)


@router.post("/ledger", status_code=201)
def create_ledger(
    body: S.LedgerIn,
    current: User = Depends(require_perm("asset:ledger:create")),
    db: Session = Depends(get_db),
):
    """手工登记出入库流水（系统单据产生的流水只读）。"""
    item_id, item_code, item_name, unit, price = svc.load_item(db, body.item_id)
    if item_id is None:
        raise BizException(R.ASSET_ITEM_NOT_FOUND)
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    loc_id, loc_code, _, loc_warehouse = svc.load_location(db, body.location_id)
    if loc_id and not warehouse_id:
        warehouse_id, warehouse_name = svc.load_warehouse(db, loc_warehouse)
    if body.direction == "out":
        stock = svc.location_stock(db, loc_id) if loc_id else svc.item_stock(db, item_id)
        if stock < float(body.quantity):
            raise BizException(R.ASSET_STOCK_NOT_ENOUGH, "出库数量超过可用库存")
    row = svc.write_ledger(
        db,
        direction=body.direction,
        item_id=item_id,
        item_code=item_code,
        item_name=item_name,
        unit=unit,
        quantity=body.quantity,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        location_id=loc_id,
        location_code=loc_code,
        unit_price=body.unit_price if body.unit_price is not None else price,
        reason="manual",
        biz_type="manual",
        biz_id=None,
        biz_no="",
        operator_id=current.id,
        operator_name=current.name or current.username,
        dept_id=body.dept_id or current.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id) or (current.dept_name or ""),
        remark=body.remark,
        happen_at=datetime.combine(body.happen_at, datetime.min.time()) if body.happen_at else None,
    )
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="ledger_create",
        biz_type="ledger", biz_id=row.id, detail={"direction": body.direction},
    )
    db.commit()
    return _ledger_out(row)


@router.put("/ledger/{lid}")
def update_ledger(
    lid: int,
    body: S.LedgerIn,
    current: User = Depends(require_perm("asset:ledger:edit")),
    db: Session = Depends(get_db),
):
    row = db.get(StockLedger, lid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if (row.biz_type or "manual") != "manual":
        raise BizException(R.ASSET_INVALID_STATE, "系统单据产生的流水不可编辑")
    svc.check_version(row, body.version)
    item_id, item_code, item_name, unit, price = svc.load_item(db, body.item_id)
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    loc_id, loc_code, _, loc_warehouse = svc.load_location(db, body.location_id)
    if loc_id and not warehouse_id:
        warehouse_id, warehouse_name = svc.load_warehouse(db, loc_warehouse)
    old_qty = float(row.quantity or 0)
    old_dir = row.direction
    old_loc_id = row.location_id
    row.direction = body.direction
    row.item_id = item_id
    row.item_code = item_code
    row.item_name = item_name
    row.unit = unit
    row.warehouse_id = warehouse_id
    row.warehouse_name = warehouse_name
    row.location_id = loc_id
    row.location_code = loc_code
    row.quantity = body.quantity
    row.unit_price = body.unit_price if body.unit_price is not None else price
    row.amount = round(float(row.unit_price or 0) * float(body.quantity), 2)
    row.dept_id = body.dept_id or row.dept_id
    row.dept_name = svc.load_dept_name(db, body.dept_id) or row.dept_name
    row.remark = body.remark
    if body.happen_at:
        row.happen_at = datetime.combine(body.happen_at, datetime.min.time())
    # 数量/方向/库位变更时先回退旧占用再按新值占用
    svc.apply_location_stock(db, old_loc_id, -(old_qty if old_dir == "in" else -old_qty))
    svc.apply_location_stock(db, loc_id, body.quantity if body.direction == "in" else -body.quantity)
    row.version += 1
    row.update_by = current.id
    row.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="ledger_update",
        biz_type="ledger", biz_id=lid,
    )
    db.commit()
    return _ledger_out(row)


@router.delete("/ledger/{lid}")
def delete_ledger(
    lid: int,
    current: User = Depends(require_perm("asset:ledger:delete")),
    db: Session = Depends(get_db),
):
    row = db.get(StockLedger, lid)
    if not row or row.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    if (row.biz_type or "manual") != "manual":
        raise BizException(R.ASSET_INVALID_STATE, "系统单据产生的流水不可删除")
    svc.apply_location_stock(
        db, row.location_id, -(float(row.quantity or 0) if row.direction == "in" else -float(row.quantity or 0))
    )
    row.deleted = 1
    row.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="ledger_delete",
        biz_type="ledger", biz_id=lid,
    )
    db.commit()
    return None


@router.post("/ledger/export")
def export_ledger(
    request: Request,
    current: User = Depends(require_perm("asset:ledger:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _ledger_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    payload = export_xlsx_styled(
        [_ledger_out(r) for r in db.scalars(stmt).all()], LEDGER_EXPORT_COLS, "asset_ledger"
    )
    audit(
        db, user_id=current.id, module="asset", action="ledger_export",
        detail={"count": 1}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_ledger')}"},
    )


# ---------------- 库存盘点 ----------------


def _count_out(c: StockCount) -> dict:
    return {
        "id": c.id,
        "countNo": c.count_no,
        "warehouseId": c.warehouse_id,
        "warehouseName": c.warehouse_name or "",
        "countDate": _d(c.count_date),
        "totalQty": float(c.total_qty or 0),
        "diffCount": c.diff_count,
        "operatorId": c.operator_id,
        "operatorName": c.operator_name or "",
        "remark": c.remark or "",
        "status": c.status,
        "statusText": _text(STATUS_CN, c.status),
        "items": [
            {
                "id": i.id,
                "itemId": i.item_id,
                "itemCode": i.item_code or "",
                "itemName": i.item_name,
                "unit": i.unit or "",
                "locationId": i.location_id,
                "locationCode": i.location_code or "",
                "bookQty": float(i.book_qty or 0),
                "actualQty": float(i.actual_qty or 0),
                "diffQty": float(i.diff_qty or 0),
                "price": _n(i.price),
                "diffAmount": _n(i.diff_amount),
                "reason": i.reason or "",
            }
            for i in (c.items or [])
            if not i.deleted
        ],
        "version": c.version,
        "createTime": _t(c.create_time),
        "updateTime": _t(c.update_time),
    }


def _count_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(StockCount),
        StockCount,
        request.query_params,
        db,
        page,
        search_cols=["count_no", "warehouse_name", "operator_name"],
        filter_cols={"status", "warehouse_id"},
        range_cols={"count_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "count_no", "count_date", "status"},
    )


@router.get("/counts")
def list_counts(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:count:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _count_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_count_out(c) for c in rows], "total": total, "page": page, "size": size}


@router.get("/counts/counts")
def stock_count_counts(
    user: User = Depends(require_perm("asset:count:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, StockCount, ("draft", "counting", "finished"))


@router.get("/counts/{cid}")
def get_count(
    cid: int,
    user: User = Depends(require_perm("asset:count:list")),
    db: Session = Depends(get_db),
):
    c = db.get(StockCount, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _count_out(c)


@router.post("/counts", status_code=201)
def create_count(
    body: S.StockCountIn,
    current: User = Depends(require_perm("asset:count:create")),
    db: Session = Depends(get_db),
):
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    c = StockCount(
        count_no=svc.next_asset_no(db, "asset_count"),
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        count_date=body.count_date or date.today(),
        total_qty=len(body.items),
        diff_count=0,
        operator_id=body.operator_id or current.id,
        operator_name=body.operator_name or (current.name or current.username),
        remark=body.remark,
        status="draft",
        create_by=current.id,
    )
    for it in body.items:
        item_id, item_code, item_name, unit, price = svc.load_item(db, it.item_id)
        loc_id, loc_code, _, _ = svc.load_location(db, it.location_id)
        book = float(it.book_qty)
        actual = float(it.actual_qty)
        c.items.append(
            StockCountItem(
                item_id=item_id,
                item_code=item_code or it.item_code,
                item_name=it.item_name,
                unit=unit or it.unit,
                location_id=loc_id,
                location_code=loc_code,
                book_qty=book,
                actual_qty=actual,
                diff_qty=round(actual - book, 2),
                price=price,
                diff_amount=round((actual - book) * float(price or 0), 2),
                reason=it.reason,
            )
        )
    db.add(c)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="count_create",
        biz_type="stock_count", biz_id=c.id,
    )
    db.commit()
    return _count_out(c)


@router.put("/counts/{cid}")
def update_count(
    cid: int,
    body: S.StockCountIn,
    current: User = Depends(require_perm("asset:count:edit")),
    db: Session = Depends(get_db),
):
    c = db.get(StockCount, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c.status, ("draft", "counting"), "已盘点单据只读，不能编辑")
    svc.check_version(c, body.version)
    warehouse_id, warehouse_name = svc.load_warehouse(db, body.warehouse_id)
    c.warehouse_id = warehouse_id
    c.warehouse_name = warehouse_name
    c.count_date = body.count_date or c.count_date
    c.operator_id = body.operator_id or c.operator_id
    c.operator_name = body.operator_name or c.operator_name
    c.remark = body.remark
    c.total_qty = len(body.items)
    c.items = []
    diff_count = 0
    for it in body.items:
        item_id, item_code, item_name, unit, price = svc.load_item(db, it.item_id)
        loc_id, loc_code, _, _ = svc.load_location(db, it.location_id)
        book = float(it.book_qty)
        actual = float(it.actual_qty)
        diff = round(actual - book, 2)
        if diff != 0:
            diff_count += 1
        c.items.append(
            StockCountItem(
                item_id=item_id,
                item_code=item_code or it.item_code,
                item_name=it.item_name,
                unit=unit or it.unit,
                location_id=loc_id,
                location_code=loc_code,
                book_qty=book,
                actual_qty=actual,
                diff_qty=diff,
                price=price,
                diff_amount=round(diff * float(price or 0), 2),
                reason=it.reason,
            )
        )
    c.diff_count = diff_count
    c.version += 1
    c.update_by = current.id
    c.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="count_update",
        biz_type="stock_count", biz_id=cid,
    )
    db.commit()
    return _count_out(c)


@router.delete("/counts/{cid}")
def delete_count(
    cid: int,
    current: User = Depends(require_perm("asset:count:delete")),
    db: Session = Depends(get_db),
):
    c = db.get(StockCount, cid)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c.status, ("draft", "counting"), "已盘点单据不能删除")
    c.deleted = 1
    c.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="count_delete",
        biz_type="stock_count", biz_id=cid,
    )
    db.commit()
    return None


@router.post("/counts/{cid}/start")
def start_count(
    cid: int,
    current: User = Depends(require_perm("asset:count:start")),
    db: Session = Depends(get_db),
):
    c = db.get(StockCount, cid, with_for_update=True)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c.status, ("draft",), "仅草稿盘点单可开始盘点")
    c.status = "counting"
    c.version += 1
    c.update_by = current.id
    c.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="count_start",
        biz_type="stock_count", biz_id=cid, detail={"countNo": c.count_no},
    )
    db.commit()
    return _count_out(c)


@router.post("/counts/{cid}/finish")
def finish_count(
    cid: int,
    current: User = Depends(require_perm("asset:count:finish")),
    db: Session = Depends(get_db),
):
    """盘点完成：差异写入库存台账（盘盈入/盘亏出）。"""
    c = db.get(StockCount, cid, with_for_update=True)
    if not c or c.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(c.status, ("draft", "counting"), "仅未完成盘点单可结盘")
    for line in [i for i in (c.items or []) if not i.deleted]:
        diff = float(line.diff_qty or 0)
        if diff == 0:
            continue
        svc.write_ledger(
            db,
            direction="in" if diff > 0 else "out",
            item_id=line.item_id,
            item_code=line.item_code or "",
            item_name=line.item_name,
            unit=line.unit or "",
            quantity=abs(diff),
            warehouse_id=c.warehouse_id,
            warehouse_name=c.warehouse_name,
            location_id=line.location_id,
            location_code=line.location_code or "",
            unit_price=_n(line.price),
            reason="count",
            biz_type="stock_count",
            biz_id=c.id,
            biz_no=c.count_no,
            operator_id=current.id,
            operator_name=current.name or current.username,
            dept_id=current.dept_id,
            dept_name=current.dept_name or "",
            remark=line.reason or "",
        )
    c.status = "finished"
    c.diff_count = len([i for i in (c.items or []) if not i.deleted and float(i.diff_qty or 0) != 0])
    c.version += 1
    c.update_by = current.id
    c.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="count_finish",
        biz_type="stock_count", biz_id=cid, detail={"countNo": c.count_no, "diffCount": c.diff_count},
    )
    db.commit()
    return _count_out(c)


@router.post("/counts/export")
def export_counts(
    request: Request,
    current: User = Depends(require_perm("asset:count:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _count_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    payload = export_xlsx_styled(
        [_count_out(c) for c in db.scalars(stmt).all()], COUNT_EXPORT_COLS, "asset_counts"
    )
    audit(
        db, user_id=current.id, module="asset", action="count_export",
        detail={"count": 1}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_counts')}"},
    )


# ---------------- 样车样件台账 ----------------


def _prototype_out(p: Prototype) -> dict:
    return {
        "id": p.id,
        "code": p.code,
        "name": p.name,
        "kind": p.kind or "",
        "kindText": _text(KIND_CN, p.kind),
        "model": p.model or "",
        "vin": p.vin or "",
        "deptId": p.dept_id,
        "deptName": p.dept_name or "",
        "locationId": p.location_id,
        "locationName": p.location_name or "",
        "purchaseDate": _d(p.purchase_date),
        "value": _n(p.value),
        "remark": p.remark or "",
        "status": p.status,
        "statusText": _text(STATUS_CN, p.status),
        "version": p.version,
        "createTime": _t(p.create_time),
        "updateTime": _t(p.update_time),
    }


def _prototype_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(Prototype),
        Prototype,
        request.query_params,
        db,
        page,
        search_cols=["code", "name", "model", "vin"],
        filter_cols={"status", "kind", "dept_id", "location_id"},
        range_cols={"purchase_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "code", "name", "value", "status"},
    )


@router.get("/prototypes")
def list_prototypes(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:prototype:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _prototype_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_prototype_out(p) for p in rows], "total": total, "page": page, "size": size}


@router.get("/prototypes/counts")
def prototype_counts(
    user: User = Depends(require_perm("asset:prototype:list")),
    db: Session = Depends(get_db),
):
    return _counts(db, Prototype, ("in_stock", "loaned", "maintenance", "scrapped"))


@router.get("/prototypes/all")
def list_all_prototypes(
    user: User = Depends(require_perm("asset:prototype:list")),
    db: Session = Depends(get_db),
):
    rows = db.scalars(select(Prototype).where(Prototype.deleted == 0).order_by(Prototype.code)).all()
    return [
        {"id": p.id, "code": p.code, "name": p.name, "model": p.model or "", "status": p.status}
        for p in rows
    ]


@router.get("/prototypes/{pid}")
def get_prototype(
    pid: int,
    user: User = Depends(require_perm("asset:prototype:list")),
    db: Session = Depends(get_db),
):
    p = db.get(Prototype, pid)
    if not p or p.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    data = _prototype_out(p)
    loans = db.scalars(
        select(PrototypeLoan)
        .where(PrototypeLoan.prototype_id == pid, PrototypeLoan.deleted == 0)
        .order_by(PrototypeLoan.id.desc())
    ).all()
    data["loans"] = [_prototype_loan_out(loan) for loan in loans]
    return data


@router.post("/prototypes", status_code=201)
def create_prototype(
    body: S.PrototypeIn,
    current: User = Depends(require_perm("asset:prototype:create")),
    db: Session = Depends(get_db),
):
    exists = db.scalar(select(Prototype.id).where(Prototype.code == body.code, Prototype.deleted == 0))
    if exists:
        raise BizException(R.ASSET_CODE_DUPLICATE, "样件编号已存在")
    _, _, loc_name, _ = svc.load_location(db, body.location_id)
    p = Prototype(
        code=body.code,
        name=body.name,
        kind=body.kind,
        model=body.model,
        vin=body.vin,
        dept_id=body.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id) or (current.dept_name or ""),
        location_id=body.location_id,
        location_name=loc_name,
        purchase_date=body.purchase_date,
        value=body.value,
        remark=body.remark,
        status=body.status,
        create_by=current.id,
    )
    db.add(p)
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="prototype_create",
        biz_type="prototype", biz_id=p.id,
    )
    db.commit()
    return _prototype_out(p)


@router.put("/prototypes/{pid}")
def update_prototype(
    pid: int,
    current: User = Depends(require_perm("asset:prototype:edit")),
    body: S.PrototypeIn = None,
    db: Session = Depends(get_db),
):
    p = db.get(Prototype, pid)
    if not p or p.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_version(p, body.version)
    _, _, loc_name, _ = svc.load_location(db, body.location_id)
    p.code = body.code
    p.name = body.name
    p.kind = body.kind
    p.model = body.model
    p.vin = body.vin
    p.dept_id = body.dept_id
    p.dept_name = svc.load_dept_name(db, body.dept_id) or p.dept_name
    p.location_id = body.location_id
    p.location_name = loc_name
    p.purchase_date = body.purchase_date
    p.value = body.value
    p.remark = body.remark
    p.status = body.status
    p.version += 1
    p.update_by = current.id
    p.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="prototype_update",
        biz_type="prototype", biz_id=pid,
    )
    db.commit()
    return _prototype_out(p)


@router.delete("/prototypes/{pid}")
def delete_prototype(
    pid: int,
    current: User = Depends(require_perm("asset:prototype:delete")),
    db: Session = Depends(get_db),
):
    p = db.get(Prototype, pid)
    if not p or p.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    open_loan = svc.open_prototype_loan(db, pid)
    if open_loan:
        raise BizException(R.ASSET_INVALID_STATE, "样件尚有未归还的借出记录")
    p.deleted = 1
    p.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="prototype_delete",
        biz_type="prototype", biz_id=pid,
    )
    db.commit()
    return None


@router.post("/prototypes/export")
def export_prototypes(
    request: Request,
    current: User = Depends(require_perm("asset:prototype:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _prototype_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    payload = export_xlsx_styled(
        [_prototype_out(p) for p in db.scalars(stmt).all()], PROTOTYPE_EXPORT_COLS, "asset_prototypes"
    )
    audit(
        db, user_id=current.id, module="asset", action="prototype_export",
        detail={"count": 1}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_prototypes')}"},
    )


# ---------------- 样件出借归还 ----------------


def _prototype_loan_out(loan: PrototypeLoan) -> dict:
    state = svc.loan_status_text(loan.status, loan.due_date)
    return {
        "id": loan.id,
        "loanNo": loan.loan_no,
        "prototypeId": loan.prototype_id,
        "prototypeCode": loan.prototype_code or "",
        "prototypeName": loan.prototype_name or "",
        "borrowerId": loan.borrower_id,
        "borrowerName": loan.borrower_name or "",
        "deptId": loan.dept_id,
        "deptName": loan.dept_name or "",
        "loanDate": _d(loan.loan_date),
        "dueDate": _d(loan.due_date),
        "returnDate": _d(loan.return_date),
        "purpose": loan.purpose or "",
        "handlerId": loan.handler_id,
        "handlerName": loan.handler_name or "",
        "remark": loan.remark or "",
        "status": loan.status,
        "statusText": _text(STATUS_CN, state),
        "version": loan.version,
        "createTime": _t(loan.create_time),
        "updateTime": _t(loan.update_time),
    }


def _prototype_loan_filtered(db: Session, request: Request, page: PageParams):
    return apply_list_filters(
        select(PrototypeLoan),
        PrototypeLoan,
        request.query_params,
        db,
        page,
        search_cols=["loan_no", "prototype_code", "prototype_name", "borrower_name"],
        filter_cols={"status", "prototype_id", "borrower_id", "dept_id"},
        range_cols={"loan_date", "due_date", "return_date", "create_time"},
        sort_cols={"update_time", "create_time", "id", "loan_no", "loan_date", "due_date", "status"},
    )


@router.get("/prototype-loans")
def list_prototype_loans(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:prototypeLoan:list")),
    db: Session = Depends(get_db),
):
    stmt, total = _prototype_loan_filtered(db, request, PageParams(page=page, size=size))
    rows = db.scalars(stmt).all()
    return {"items": [_prototype_loan_out(loan) for loan in rows], "total": total, "page": page, "size": size}


@router.get("/prototype-loans/counts")
def prototype_loan_counts(
    user: User = Depends(require_perm("asset:prototypeLoan:list")),
    db: Session = Depends(get_db),
):
    data = _counts(db, PrototypeLoan, ("borrowed", "returned"))
    overdue = db.scalar(
        select(func.count())
        .select_from(PrototypeLoan)
        .where(
            PrototypeLoan.deleted == 0,
            PrototypeLoan.status == "borrowed",
            PrototypeLoan.due_date < date.today(),
        )
    ) or 0
    data["overdue"] = int(overdue)
    return data


@router.get("/prototype-loans/{lid}")
def get_prototype_loan(
    lid: int,
    user: User = Depends(require_perm("asset:prototypeLoan:list")),
    db: Session = Depends(get_db),
):
    loan = db.get(PrototypeLoan, lid)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    return _prototype_loan_out(loan)


@router.post("/prototype-loans", status_code=201)
def create_prototype_loan(
    body: S.PrototypeLoanIn,
    current: User = Depends(require_perm("asset:prototypeLoan:create")),
    db: Session = Depends(get_db),
):
    _, code, name = svc.load_prototype(db, body.prototype_id)
    if svc.open_prototype_loan(db, body.prototype_id):
        raise BizException(R.ASSET_LOAN_NOT_RETURNED, "该样件尚未归还，不能再次借出")
    p = db.get(Prototype, body.prototype_id)
    loan = PrototypeLoan(
        loan_no=svc.next_asset_no(db, "asset_prototype_loan"),
        prototype_id=body.prototype_id,
        prototype_code=code,
        prototype_name=name,
        borrower_id=body.borrower_id or current.id,
        borrower_name=body.borrower_name or (current.name or current.username),
        dept_id=body.dept_id or current.dept_id,
        dept_name=svc.load_dept_name(db, body.dept_id) or (current.dept_name or ""),
        loan_date=body.loan_date or date.today(),
        due_date=body.due_date,
        purpose=body.purpose,
        handler_id=body.handler_id or current.id,
        handler_name=body.handler_name or (current.name or current.username),
        remark=body.remark,
        status="borrowed",
        create_by=current.id,
    )
    db.add(loan)
    if p and p.status == "in_stock":
        p.status = "loaned"
        p.update_time = datetime.now()
    db.flush()
    audit(
        db, user_id=current.id, module="asset", action="prototype_loan_create",
        biz_type="prototype_loan", biz_id=loan.id, detail={"prototypeCode": code},
    )
    db.commit()
    return _prototype_loan_out(loan)


@router.put("/prototype-loans/{lid}")
def update_prototype_loan(
    lid: int,
    body: S.PrototypeLoanIn,
    current: User = Depends(require_perm("asset:prototypeLoan:edit")),
    db: Session = Depends(get_db),
):
    loan = db.get(PrototypeLoan, lid)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(loan.status, ("borrowed",), "已归还记录只读，不能编辑")
    svc.check_version(loan, body.version)
    _, code, name = svc.load_prototype(db, body.prototype_id)
    loan.prototype_id = body.prototype_id
    loan.prototype_code = code
    loan.prototype_name = name
    loan.borrower_id = body.borrower_id or loan.borrower_id
    loan.borrower_name = body.borrower_name or loan.borrower_name
    loan.dept_id = body.dept_id or loan.dept_id
    loan.dept_name = svc.load_dept_name(db, body.dept_id) or loan.dept_name
    loan.loan_date = body.loan_date or loan.loan_date
    loan.due_date = body.due_date
    loan.purpose = body.purpose
    loan.handler_id = body.handler_id or loan.handler_id
    loan.handler_name = body.handler_name or loan.handler_name
    loan.remark = body.remark
    loan.version += 1
    loan.update_by = current.id
    loan.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="prototype_loan_update",
        biz_type="prototype_loan", biz_id=lid,
    )
    db.commit()
    return _prototype_loan_out(loan)


@router.delete("/prototype-loans/{lid}")
def delete_prototype_loan(
    lid: int,
    current: User = Depends(require_perm("asset:prototypeLoan:delete")),
    db: Session = Depends(get_db),
):
    loan = db.get(PrototypeLoan, lid)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(loan.status, ("borrowed",), "已归还记录不能删除")
    p = db.get(Prototype, loan.prototype_id)
    if p and p.status == "loaned" and not svc.open_prototype_loan(db, loan.prototype_id):
        p.status = "in_stock"
        p.update_time = datetime.now()
    loan.deleted = 1
    loan.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="prototype_loan_delete",
        biz_type="prototype_loan", biz_id=lid,
    )
    db.commit()
    return None


@router.post("/prototype-loans/{lid}/return")
def return_prototype_loan(
    lid: int,
    body: S.LoanReturnIn | None = None,
    current: User = Depends(require_perm("asset:prototypeLoan:return")),
    db: Session = Depends(get_db),
):
    loan = db.get(PrototypeLoan, lid, with_for_update=True)
    if not loan or loan.deleted:
        raise BizException(R.GENERIC_NOT_FOUND)
    svc.check_editable(loan.status, ("borrowed",), "该借出单已归还")
    loan.return_date = (body.return_date if body and body.return_date else date.today())
    if body and body.remark:
        loan.remark = body.remark
    loan.status = "returned"
    loan.version += 1
    loan.update_by = current.id
    loan.update_time = datetime.now()
    p = db.get(Prototype, loan.prototype_id)
    if p and p.status == "loaned":
        p.status = "in_stock"
        p.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="prototype_loan_return",
        biz_type="prototype_loan", biz_id=lid, detail={"loanNo": loan.loan_no},
    )
    db.commit()
    return _prototype_loan_out(loan)


@router.post("/prototype-loans/export")
def export_prototype_loans(
    request: Request,
    current: User = Depends(require_perm("asset:prototypeLoan:list:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = _prototype_loan_filtered(db, request, SimpleNamespace(page=1, size=100_000))
    payload = export_xlsx_styled(
        [_prototype_loan_out(loan) for loan in db.scalars(stmt).all()],
        PROTOTYPE_LOAN_EXPORT_COLS,
        "asset_prototype_loans",
    )
    audit(
        db, user_id=current.id, module="asset", action="prototype_loan_export",
        detail={"count": 1}, trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('asset_prototype_loans')}"
        },
    )
