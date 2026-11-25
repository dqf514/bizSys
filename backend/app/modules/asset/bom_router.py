"""资产模块路由（BOM 物料清单部分）/api/v1/asset。

BOM 覆盖：父子结构（多级展开）、版本管理（同一父件仅一个生效版本）、用量（理论需求 vs 实际领用）。
统一框架：父件与子件均取 `ast_item` 存货档案；部门 → sys_dept；权限 → sys_menu。
"""

from datetime import date, datetime
from types import SimpleNamespace

from fastapi import APIRouter, Depends, Query, Request, Response
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
from app.modules.asset import schemas as S
from app.modules.asset import service as svc
from app.modules.asset.models import Bom, BomLine, Item
from app.modules.auth.models import User
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/asset", tags=["asset"], route_class=EnvelopeRoute)

BOM_STATUS_CN = {
    "draft": "草稿",
    "effective": "已生效",
    "obsolete": "已作废",
}

STAGNANT_LEVEL_CN = {
    "normal": "正常",
    "slow": "慢动销",
    "stagnant": "呆滞",
    "dead": "呆死",
}

BOM_EXPORT_COLS = [
    {"key": "bomNo", "label": "BOM 编号", "width": 18},
    {"key": "parentItemCode", "label": "父件编码", "width": 16},
    {"key": "parentItemName", "label": "父件名称", "width": 24},
    {"key": "parentSpec", "label": "规格型号", "width": 20},
    {"key": "version", "label": "版本", "width": 10},
    {"key": "lineCount", "label": "子件行数", "width": 10},
    {"key": "effectiveDate", "label": "生效日期", "width": 12},
    {"key": "statusText", "label": "状态", "width": 10},
    {"key": "createTime", "label": "创建时间", "width": 19},
]


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


def _load_bom(db: Session, bid: int) -> Bom:
    bom = db.get(Bom, bid)
    if not bom or bom.deleted:
        raise BizException(R.ASSET_BOM_NOT_FOUND)
    return bom


def _line_out(line: BomLine) -> dict:
    return {
        "id": line.id,
        "bomId": line.bom_id,
        "itemId": line.item_id,
        "itemCode": line.item_code or "",
        "itemName": line.item_name or "",
        "spec": line.spec or "",
        "unit": line.unit or "",
        "qty": float(line.qty or 0),
        "lossRate": float(line.loss_rate or 0),
        "requiredQty": svc.bom_line_qty(line),
        "refDesignator": line.ref_designator or "",
        "position": line.position or "",
        "remark": line.remark or "",
    }


def _bom_out(bom: Bom, with_lines: bool = True) -> dict:
    data = {
        "id": bom.id,
        "bomNo": bom.bom_no,
        "parentItemId": bom.parent_item_id,
        "parentItemCode": bom.parent_item_code or "",
        "parentItemName": bom.parent_item_name or "",
        "parentSpec": bom.parent_spec or "",
        "version": bom.bom_version,
        "status": bom.status,
        "statusText": _text(BOM_STATUS_CN, bom.status),
        "effectiveDate": _d(bom.effective_date),
        "lineCount": len(bom.lines or []),
        "remark": bom.remark or "",
        "lockVersion": bom.version,
        "createTime": _t(bom.create_time),
        "updateTime": _t(bom.update_time),
    }
    if with_lines:
        data["lines"] = [_line_out(ln) for ln in (bom.lines or [])]
    return data


def _replace_lines(db: Session, bom: Bom, lines: list[S.BomLineIn]) -> None:
    """整表替换子件行（仅草稿可编辑）。

    用 ORM 级 clear()（delete-orphan 级联）删除旧行，避免批量 DELETE 绕过 ORM
    导致 flush 时重复删除告警。
    """
    bom.lines.clear()
    for ln in lines:
        bom.lines.append(
            BomLine(
                item_id=ln.item_id,
                item_code=ln.item_code,
                item_name=ln.item_name,
                spec=ln.spec,
                unit=ln.unit,
                qty=ln.qty,
                loss_rate=ln.loss_rate,
                ref_designator=ln.ref_designator,
                position=ln.position,
                remark=ln.remark,
            )
        )
    bom.line_count = len(lines)


def _fill_parent(db: Session, bom: Bom, parent_item_id: int) -> None:
    parent = db.get(Item, parent_item_id)
    if not parent or parent.deleted:
        raise BizException(R.ASSET_ITEM_NOT_FOUND)
    bom.parent_item_id = parent.id
    bom.parent_item_code = parent.code
    bom.parent_item_name = parent.name
    bom.parent_spec = parent.spec or ""


def _validate_lines(db: Session, bom: Bom, lines: list[S.BomLineIn]) -> None:
    """子件校验：不得引用自身（防自环）；带出存货档案信息。"""
    for ln in lines:
        if ln.item_id:
            child = db.get(Item, ln.item_id)
            if not child or child.deleted:
                raise BizException(R.ASSET_ITEM_NOT_FOUND, f"子件存货不存在：{ln.item_id}")
            if child.id == bom.parent_item_id:
                raise BizException(R.ASSET_INVALID_STATE, "子件不能是父件本身")
            ln.item_code = child.code
            ln.item_name = child.name
            ln.spec = child.spec or ""
            ln.unit = child.unit or ""


# ---------------- BOM 列表与明细 ----------------


@router.get("/boms")
def list_boms(
    request: Request,
    page: int = Query(1, ge=1, le=PAGE_MAX),
    size: int = Query(20, ge=1, le=200),
    user: User = Depends(require_perm("asset:bom:list")),
    db: Session = Depends(get_db),
):
    stmt, total = apply_list_filters(
        select(Bom),
        Bom,
        request.query_params,
        db,
        PageParams(page=page, size=size),
        search_cols=["bom_no", "parent_item_code", "parent_item_name", "parent_spec", "bom_version"],
        filter_cols={"status", "parent_item_id"},
        range_cols={"create_time", "effective_date"},
        sort_cols={"create_time", "update_time", "id", "bom_no", "bom_version", "status"},
    )
    rows = list(db.scalars(stmt).all())
    return {
        "items": [_bom_out(b, with_lines=False) for b in rows],
        "total": total,
        "page": page,
        "size": size,
    }


@router.get("/boms/counts")
def bom_counts(
    user: User = Depends(require_perm("asset:bom:list")),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(Bom.status, func.count()).where(Bom.deleted == 0).group_by(Bom.status)
    ).all()
    data = {"draft": 0, "effective": 0, "obsolete": 0}
    data.update({s: n for s, n in rows if s in data})
    data["all"] = sum(data.values())
    return data


@router.get("/boms/{bid}")
def get_bom(
    bid: int,
    user: User = Depends(require_perm("asset:bom:list")),
    db: Session = Depends(get_db),
):
    return _bom_out(_load_bom(db, bid))


@router.get("/boms/{bid}/explode")
def explode_bom(
    bid: int,
    max_depth: int = Query(5, ge=1, le=10),
    user: User = Depends(require_perm("asset:bom:list")),
    db: Session = Depends(get_db),
):
    """多级展开：子件本身是总成时按其生效 BOM 继续下钻（带循环检测）。"""
    bom = _load_bom(db, bid)
    return {
        "bomId": bom.id,
        "bomNo": bom.bom_no,
        "parentItemName": bom.parent_item_name,
        "version": bom.bom_version,
        "tree": svc.bom_explode(db, bom, max_depth=max_depth),
    }


@router.get("/boms/{bid}/usage")
def bom_usage(
    bid: int,
    qty: float = Query(1, gt=0, le=9999999999.99),
    user: User = Depends(require_perm("asset:bom:list")),
    db: Session = Depends(get_db),
):
    """用量对比：理论需求（按父件数量折算）vs 子件历史实际领用。"""
    bom = _load_bom(db, bid)
    rows = svc.bom_usage(db, bom, parent_qty=qty)
    return {
        "bomId": bom.id,
        "bomNo": bom.bom_no,
        "parentItemName": bom.parent_item_name,
        "parentQty": qty,
        "lines": rows,
    }


@router.get("/items/{iid}/bom-refs")
def item_bom_refs(
    iid: int,
    user: User = Depends(require_any_perm("asset:bom:list", "asset:material:list")),
    db: Session = Depends(get_db),
):
    """某存货的 BOM 关联：作为父件的 BOM + 作为子件被引用的 BOM。"""
    item = db.get(Item, iid)
    if not item or item.deleted:
        raise BizException(R.ASSET_ITEM_NOT_FOUND)
    as_parent = db.scalars(
        select(Bom).where(Bom.parent_item_id == iid, Bom.deleted == 0).order_by(Bom.id.desc())
    ).all()
    child_line_rows = db.execute(
        select(BomLine, Bom)
        .join(Bom, Bom.id == BomLine.bom_id)
        .where(BomLine.item_id == iid, BomLine.deleted == 0, Bom.deleted == 0)
        .order_by(Bom.id.desc())
    ).all()
    return {
        "itemId": iid,
        "itemCode": item.code,
        "itemName": item.name,
        "asParent": [_bom_out(b, with_lines=False) for b in as_parent],
        "asChild": [
            {
                "bomId": bom.id,
                "bomNo": bom.bom_no,
                "parentItemName": bom.parent_item_name,
                "version": bom.bom_version,
                "status": bom.status,
                "qty": float(line.qty or 0),
                "lossRate": float(line.loss_rate or 0),
                "requiredQty": svc.bom_line_qty(line),
                "position": line.position or "",
            }
            for line, bom in child_line_rows
        ],
    }


# ---------------- BOM 维护 ----------------


@router.post("/boms", status_code=201)
def create_bom(
    body: S.BomIn,
    current: User = Depends(require_perm("asset:bom:create")),
    db: Session = Depends(get_db),
):
    svc.check_bom_version_unique(db, body.parent_item_id, body.bom_version)
    bom = Bom(
        bom_no="",
        parent_item_id=body.parent_item_id,
        bom_version=body.bom_version,
        status="draft",
        effective_date=body.effective_date,
        remark=body.remark,
        create_by=current.id,
    )
    _fill_parent(db, bom, body.parent_item_id)
    db.add(bom)
    db.flush()
    _validate_lines(db, bom, body.lines)
    _replace_lines(db, bom, body.lines)
    bom.bom_no = svc.next_asset_no(db, "asset_bom")
    audit(
        db, user_id=current.id, module="asset", action="bom_create",
        biz_type="bom", biz_id=bom.id,
        detail={"bomNo": bom.bom_no, "version": bom.bom_version},
    )
    db.commit()
    return _bom_out(bom)


@router.put("/boms/{bid}")
def update_bom(
    bid: int,
    body: S.BomIn,
    current: User = Depends(require_perm("asset:bom:edit")),
    db: Session = Depends(get_db),
):
    bom = _load_bom(db, bid)
    svc.check_editable(bom.status, ("draft",), "只有草稿状态的 BOM 可以修改")
    svc.check_version(bom, body.version)
    svc.check_bom_version_unique(db, body.parent_item_id, body.bom_version, exclude_id=bom.id)
    _fill_parent(db, bom, body.parent_item_id)
    bom.bom_version = body.bom_version
    bom.effective_date = body.effective_date
    bom.remark = body.remark
    _validate_lines(db, bom, body.lines)
    _replace_lines(db, bom, body.lines)
    bom.update_by = current.id
    bom.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="bom_update",
        biz_type="bom", biz_id=bid,
    )
    db.commit()
    return _bom_out(bom)


@router.post("/boms/{bid}/activate")
def activate_bom(
    bid: int,
    current: User = Depends(require_perm("asset:bom:edit")),
    db: Session = Depends(get_db),
):
    """生效 BOM：同一父件的其它生效版本自动作废。"""
    bom = _load_bom(db, bid)
    svc.check_editable(bom.status, ("draft", "obsolete"), "已生效的 BOM 不能重复生效")
    if not (bom.lines or []):
        raise BizException(R.ASSET_INVALID_STATE, "BOM 没有子件，不能生效")
    svc.activate_bom(db, bom)
    bom.status = "effective"
    if bom.effective_date is None:
        bom.effective_date = date.today()
    bom.update_by = current.id
    bom.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="bom_activate",
        biz_type="bom", biz_id=bid,
        detail={"bomNo": bom.bom_no, "version": bom.bom_version},
    )
    db.commit()
    return _bom_out(bom)


@router.post("/boms/{bid}/obsolete")
def obsolete_bom(
    bid: int,
    current: User = Depends(require_perm("asset:bom:edit")),
    db: Session = Depends(get_db),
):
    """作废 BOM（停用某个父件的当前版本）。"""
    bom = _load_bom(db, bid)
    svc.check_editable(bom.status, ("effective",), "只有已生效的 BOM 可以作废")
    bom.status = "obsolete"
    bom.update_by = current.id
    bom.update_time = datetime.now()
    audit(
        db, user_id=current.id, module="asset", action="bom_obsolete",
        biz_type="bom", biz_id=bid,
    )
    db.commit()
    return _bom_out(bom)


@router.post("/boms/{bid}/copy")
def copy_bom(
    bid: int,
    current: User = Depends(require_perm("asset:bom:create")),
    db: Session = Depends(get_db),
):
    """复制为新版本草稿：版本号自动 +0.1。"""
    src = _load_bom(db, bid)
    try:
        major, minor = str(src.bom_version).lstrip("Vv").split(".", 1)
        next_version = f"V{int(major)}.{int(minor) + 1}"
    except ValueError:
        next_version = f"{src.bom_version}-COPY"
    svc.check_bom_version_unique(db, src.parent_item_id, next_version)
    bom = Bom(
        bom_no="",
        parent_item_id=src.parent_item_id,
        parent_item_code=src.parent_item_code,
        parent_item_name=src.parent_item_name,
        parent_spec=src.parent_spec,
        bom_version=next_version,
        status="draft",
        remark=src.remark,
        create_by=current.id,
    )
    db.add(bom)
    db.flush()
    _replace_lines(db, bom, [
        S.BomLineIn(
            item_id=ln.item_id,
            item_code=ln.item_code,
            item_name=ln.item_name,
            spec=ln.spec,
            unit=ln.unit,
            qty=float(ln.qty or 0),
            loss_rate=float(ln.loss_rate or 0),
            ref_designator=ln.ref_designator,
            position=ln.position,
            remark=ln.remark,
        )
        for ln in (src.lines or [])
    ])
    bom.bom_no = svc.next_asset_no(db, "asset_bom")
    audit(
        db, user_id=current.id, module="asset", action="bom_copy",
        biz_type="bom", biz_id=bom.id,
        detail={"fromBomNo": src.bom_no, "version": next_version},
    )
    db.commit()
    return _bom_out(bom)


@router.delete("/boms/{bid}")
def delete_bom(
    bid: int,
    current: User = Depends(require_perm("asset:bom:delete")),
    db: Session = Depends(get_db),
):
    bom = _load_bom(db, bid)
    svc.check_editable(bom.status, ("draft",), "只有草稿状态的 BOM 可以删除")
    recycle.soft_delete(db, Bom, bom, user=current, module="asset", resource="Bom")
    bom.update_by = current.id
    bom.update_time = datetime.now()
    bom.lines.clear()  # delete-orphan 级联删除子件行
    audit(
        db, user_id=current.id, module="asset", action="bom_delete",
        biz_type="bom", biz_id=bid,
    )
    db.commit()
    return {"id": bid}


@router.post("/boms/export")
def export_boms(
    request: Request,
    current: User = Depends(require_perm("asset:bom:export")),
    db: Session = Depends(get_db),
):
    stmt, _ = apply_list_filters(
        select(Bom),
        Bom,
        request.query_params,
        db,
        SimpleNamespace(page=1, size=100_000),
        search_cols=["bom_no", "parent_item_code", "parent_item_name", "parent_spec", "bom_version"],
        filter_cols={"status", "parent_item_id"},
        range_cols={"create_time", "effective_date"},
        sort_cols={"create_time", "update_time", "id", "bom_no", "bom_version", "status"},
    )
    rows = list(db.scalars(stmt).all())
    data = [_bom_out(b, with_lines=False) for b in rows]
    return Response(
        content=export_xlsx_styled(data, BOM_EXPORT_COLS, now_filename("资产BOM")),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="asset-bom.xlsx"'},
    )
