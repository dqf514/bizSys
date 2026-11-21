"""资产与库存服务：状态机约束、跨域档案装载、库存流水与折旧计算。

跨域只读引用（不新建组织/公司/权限表）：
- 部门 → `sys_dept`
- 供应公司 → `crm_customer`（往来单位）
"""

from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import response as R
from app.core.exceptions import BizException
from app.modules.asset.models import (
    Bom,
    Depreciation,
    Disposal,
    FixedAsset,
    Item,
    Location,
    Prototype,
    PrototypeLoan,
    PurchaseOrder,
    Receipt,
    StockCount,
    StockLedger,
    Tool,
    ToolLoan,
    Warehouse,
)

# ---------------- 通用校验 ----------------


def check_editable(status: str, editable: tuple[str, ...], message: str = "") -> None:
    if status not in editable:
        raise BizException(R.ASSET_INVALID_STATE, message or f"状态「{status}」不允许该操作")


def check_version(obj, version: int | None) -> None:
    if version is not None and version != obj.version:
        raise BizException(R.GENERIC_OPTIMISTIC_LOCK)


# ---------------- 单号生成 ----------------

# 资产域单号规则 → (模型, 编号列)
_NO_SOURCES: dict[str, tuple[type, str]] = {
    "asset_purchase_order": (PurchaseOrder, "order_no"),
    "asset_receipt": (Receipt, "receipt_no"),
    "asset_count": (StockCount, "count_no"),
    "asset_prototype_loan": (PrototypeLoan, "loan_no"),
    "asset_tool_loan": (ToolLoan, "loan_no"),
    "asset_disposal": (Disposal, "disposal_no"),
    "asset_bom": (Bom, "bom_no"),
}


def next_asset_no(db: Session, biz_type: str) -> str:
    """取资产域单号，自动跳过已被占用的号。

    编号计数器（sys_number_seq）在「一键清空」或管理员重置序列后可能落后于存量数据，
    直接取号会撞唯一索引；这里逐个试探，直到拿到未被占用的号。
    """
    from app.services.numbering import next_no

    model, col = _NO_SOURCES[biz_type]
    for _ in range(100):
        no = next_no(db, biz_type)
        taken = db.scalar(select(model.id).where(getattr(model, col) == no).limit(1))
        if taken is None:
            return no
    raise BizException(R.ADMIN_NUMBER_CONFLICT, f"单号生成失败（连续冲突）：{biz_type}")


# ---------------- 跨域档案装载 ----------------


def load_supplier_name(db: Session, supplier_id: int | None) -> str:
    """供应公司必须是启用的 supplier/both 往来单位（公司统一走 crm_customer）。"""
    if not supplier_id:
        return ""
    from app.modules.crm.models import Customer

    row = db.execute(
        select(Customer.name, Customer.partner_type, Customer.status).where(
            Customer.id == supplier_id, Customer.deleted == 0
        )
    ).first()
    if not row or row[1] not in ("supplier", "both") or row[2] != "enabled":
        raise BizException(R.ASSET_SUPPLIER_INVALID)
    return row[0]


def load_dept_name(db: Session, dept_id: int | None) -> str:
    """部门统一走 sys_dept。"""
    if not dept_id:
        return ""
    from app.modules.admin.models import Dept

    row = db.scalar(select(Dept.name).where(Dept.id == dept_id, Dept.deleted == 0))
    return row or ""


def load_warehouse(db: Session, warehouse_id: int | None) -> tuple[int | None, str]:
    if not warehouse_id:
        return None, ""
    w = db.get(Warehouse, warehouse_id)
    if not w or w.deleted:
        raise BizException(R.ASSET_WAREHOUSE_INVALID)
    return w.id, w.name


def load_location(db: Session, location_id: int | None) -> tuple[int | None, str, str, int | None]:
    """返回 (location_id, code, name, warehouse_id)。"""
    if not location_id:
        return None, "", "", None
    loc = db.get(Location, location_id)
    if not loc or loc.deleted:
        raise BizException(R.ASSET_LOCATION_INVALID)
    return loc.id, loc.code, loc.name, loc.warehouse_id


def load_item(db: Session, item_id: int | None) -> tuple[int | None, str, str, str, float | None]:
    """返回 (id, code, name, unit, unit_price)。"""
    if not item_id:
        return None, "", "", "", None
    it = db.get(Item, item_id)
    if not it or it.deleted:
        raise BizException(R.ASSET_ITEM_NOT_FOUND)
    price = float(it.unit_price) if it.unit_price is not None else None
    return it.id, it.code, it.name, it.unit, price


def load_prototype(db: Session, prototype_id: int) -> tuple[int, str, str]:
    p = db.get(Prototype, prototype_id)
    if not p or p.deleted:
        raise BizException(R.ASSET_ITEM_NOT_FOUND, "样件不存在")
    return p.id, p.code, p.name


def load_tool(db: Session, tool_id: int) -> tuple[int, str, str]:
    t = db.get(Tool, tool_id)
    if not t or t.deleted:
        raise BizException(R.ASSET_ITEM_NOT_FOUND, "工具不存在")
    return t.id, t.tool_no, t.name


# ---------------- 库存数量 ----------------


def item_stock(db: Session, item_id: int) -> float:
    """存货现存数量 = 入库合计 - 出库合计。"""
    rows = db.execute(
        select(StockLedger.direction, func.coalesce(func.sum(StockLedger.quantity), 0)).where(
            StockLedger.item_id == item_id, StockLedger.deleted == 0
        ).group_by(StockLedger.direction)
    ).all()
    total = 0.0
    for direction, qty in rows:
        total += float(qty) if direction == "in" else -float(qty)
    return round(total, 2)


def item_stock_map(db: Session, item_ids: list[int]) -> dict[int, float]:
    if not item_ids:
        return {}
    rows = db.execute(
        select(StockLedger.item_id, StockLedger.direction, func.coalesce(func.sum(StockLedger.quantity), 0))
        .where(StockLedger.item_id.in_(item_ids), StockLedger.deleted == 0)
        .group_by(StockLedger.item_id, StockLedger.direction)
    ).all()
    out: dict[int, float] = {i: 0.0 for i in item_ids}
    for item_id, direction, qty in rows:
        if item_id not in out:
            continue
        out[item_id] += float(qty) if direction == "in" else -float(qty)
    return {k: round(v, 2) for k, v in out.items()}


def location_stock(db: Session, location_id: int) -> float:
    row = db.scalar(
        select(func.coalesce(func.sum(StockLedger.quantity), 0)).where(
            StockLedger.location_id == location_id,
            StockLedger.deleted == 0,
            StockLedger.direction == "in",
        )
    )
    in_qty = float(row or 0)
    row = db.scalar(
        select(func.coalesce(func.sum(StockLedger.quantity), 0)).where(
            StockLedger.location_id == location_id,
            StockLedger.deleted == 0,
            StockLedger.direction == "out",
        )
    )
    return round(in_qty - float(row or 0), 2)


def apply_location_stock(db: Session, location_id: int | None, delta: float) -> None:
    """回写库位在库数量（delta 正=入库 负=出库）。"""
    if not location_id:
        return
    loc = db.get(Location, location_id, with_for_update=True)
    if not loc or loc.deleted:
        return
    loc.qty_on_hand = round(float(loc.qty_on_hand or 0) + delta, 2)


def write_ledger(
    db: Session,
    *,
    direction: str,
    item_id: int | None,
    item_code: str,
    item_name: str,
    unit: str,
    quantity: float,
    warehouse_id: int | None,
    warehouse_name: str,
    location_id: int | None,
    location_code: str,
    unit_price: float | None,
    reason: str,
    biz_type: str,
    biz_id: int | None,
    biz_no: str,
    operator_id: int | None,
    operator_name: str,
    dept_id: int | None,
    dept_name: str,
    remark: str = "",
    happen_at: datetime | None = None,
) -> StockLedger:
    """写一条库存流水并同步库位在库数量（同一事务内）。"""
    amount = round(float(unit_price or 0) * float(quantity), 2)
    row = StockLedger(
        direction=direction,
        item_id=item_id,
        item_code=item_code,
        item_name=item_name,
        unit=unit,
        warehouse_id=warehouse_id,
        warehouse_name=warehouse_name,
        location_id=location_id,
        location_code=location_code,
        quantity=quantity,
        unit_price=unit_price,
        amount=amount,
        reason=reason,
        biz_type=biz_type,
        biz_id=biz_id,
        biz_no=biz_no,
        operator_id=operator_id,
        operator_name=operator_name,
        dept_id=dept_id,
        dept_name=dept_name,
        happen_at=happen_at or datetime.now(),
        remark=remark,
    )
    db.add(row)
    apply_location_stock(db, location_id, float(quantity) if direction == "in" else -float(quantity))
    return row


# ---------------- 借还状态 ----------------


def loan_overdue(status: str, due_date: date | None) -> bool:
    return bool(status == "borrowed" and due_date and due_date < date.today())


def loan_status_text(status: str, due_date: date | None) -> str:
    return "overdue" if loan_overdue(status, due_date) else status


# ---------------- 折旧计算 ----------------


def months_elapsed(purchase_date: date | None, period: str) -> int:
    """从购置日到计提期结束的整月数（不足一月按 0 计）。"""
    if not purchase_date:
        return 0
    year, month = (int(x) for x in period.split("-"))
    months = (year - purchase_date.year) * 12 + (month - purchase_date.month)
    if purchase_date.day > 1:
        months -= 0  # 日内占比不折算整月，保持口径简单可解释
    return max(months, 0)


def depreciation_amount(asset: FixedAsset, method: str, period: str) -> float:
    """本期折旧额。

    - straight_line 平均年限法：(原值 - 残值) / 使用月数
    - double_declining 双倍余额递减：净值 × 2 / 剩余使用月数
    - sum_of_years 年数总和法：净值 × 剩余年限 / 年数总和
    """
    original = float(asset.original_value or 0)
    salvage = original * float(asset.salvage_rate or 0)
    life = max(int(asset.useful_life_months or 0), 1)
    elapsed = months_elapsed(asset.purchase_date, period)
    accum = float(asset.accum_depreciation or 0)
    depreciable = max(original - salvage - accum, 0.0)
    if depreciable <= 0:
        return 0.0
    if method == "double_declining":
        remaining = max(life - elapsed, 1)
        amount = depreciable * 2 / remaining
    elif method == "sum_of_years":
        total = life * (life + 1) / 2
        remaining_years = max(life - elapsed, 1)
        amount = depreciable * remaining_years / total
    else:
        amount = depreciable / life
    return round(min(amount, depreciable), 2)


def asset_net_value(asset: FixedAsset) -> float:
    original = float(asset.original_value or 0)
    salvage = original * float(asset.salvage_rate or 0)
    return round(max(original - float(asset.accum_depreciation or 0) - salvage, 0.0), 2)


def depreciation_rows(db: Session, asset_id: int) -> list[Depreciation]:
    return list(
        db.scalars(
            select(Depreciation)
            .where(Depreciation.asset_id == asset_id, Depreciation.deleted == 0)
            .order_by(Depreciation.period.desc(), Depreciation.id.desc())
        ).all()
    )


def open_prototype_loan(db: Session, prototype_id: int) -> PrototypeLoan | None:
    return db.scalar(
        select(PrototypeLoan)
        .where(
            PrototypeLoan.prototype_id == prototype_id,
            PrototypeLoan.status == "borrowed",
            PrototypeLoan.deleted == 0,
        )
        .order_by(PrototypeLoan.id.desc())
    )


def open_tool_loan(db: Session, tool_id: int) -> ToolLoan | None:
    return db.scalar(
        select(ToolLoan)
        .where(ToolLoan.tool_id == tool_id, ToolLoan.status == "borrowed", ToolLoan.deleted == 0)
        .order_by(ToolLoan.id.desc())
    )


# ---------------- 呆滞预警 ----------------

# 呆滞分级：按「闲置天数 / 阈值」倍数判定（阈值取存货自身的 stagnant_days）
STAGNANT_LEVELS = ("normal", "slow", "stagnant", "dead")
DEFAULT_STAGNANT_DAYS = 90


def stagnant_level(idle_days: int, threshold: int) -> str:
    """呆滞分级：normal 正常 / slow 慢动销 / stagnant 呆滞 / dead 呆死。"""
    if threshold <= 0:
        return "normal"
    if idle_days < threshold:
        return "normal"
    if idle_days < threshold * 2:
        return "slow"
    if idle_days < threshold * 3:
        return "stagnant"
    return "dead"


def item_idle_map(db: Session, items: list[Item]) -> dict[int, dict]:
    """存货的最近一次出入库时间与闲置天数。

    没有流水的存货按建档时间起算（同样视为长期未动）。
    """
    if not items:
        return {}
    item_ids = [i.id for i in items]
    rows = db.execute(
        select(StockLedger.item_id, func.max(StockLedger.happen_at))
        .where(StockLedger.item_id.in_(item_ids), StockLedger.deleted == 0)
        .group_by(StockLedger.item_id)
    ).all()
    last_move = {item_id: ts for item_id, ts in rows if item_id is not None}
    out: dict[int, dict] = {}
    today = datetime.now().date()
    for item in items:
        base = last_move.get(item.id) or item.create_time
        base_dt = base if isinstance(base, datetime) else None
        idle_days = (today - base_dt.date()).days if base_dt else 0
        out[item.id] = {"lastMoveAt": base_dt, "idleDays": max(idle_days, 0)}
    return out


def item_warning_map(db: Session, items: list[Item], stock_map: dict[int, float]) -> dict[int, dict]:
    """存货预警信息：低库存 + 呆滞分级 + 呆滞金额。"""
    if not items:
        return {}
    idle = item_idle_map(db, items)
    out: dict[int, dict] = {}
    for item in items:
        qty = float(stock_map.get(item.id, 0.0))
        info = idle.get(item.id, {"lastMoveAt": None, "idleDays": 0})
        threshold = int(item.stagnant_days or 0)
        level = stagnant_level(int(info["idleDays"]), threshold)
        price = float(item.unit_price or 0)
        out[item.id] = {
            "lastMoveAt": info["lastMoveAt"],
            "idleDays": int(info["idleDays"]),
            "stagnantDays": threshold,
            "stagnantLevel": level,
            "stagnant": level != "normal" and qty > 0,
            "stagnantAmount": round(qty * price, 2) if level != "normal" else 0.0,
        }
    return out


# ---------------- BOM ----------------

BOM_STATUSES = ("draft", "effective", "obsolete")


def bom_line_qty(line) -> float:
    """子件行理论用量 = 单位用量 × (1 + 损耗率)。"""
    qty = float(line.qty or 0)
    loss = float(line.loss_rate or 0)
    return round(qty * (1 + loss / 100), 4)


def check_bom_version_unique(db: Session, parent_item_id: int, version: str, exclude_id: int | None = None) -> None:
    """同一父件同一版本号唯一。"""
    stmt = select(Bom.id).where(
        Bom.parent_item_id == parent_item_id,
        Bom.bom_version == version,
        Bom.deleted == 0,
    )
    if exclude_id:
        stmt = stmt.where(Bom.id != exclude_id)
    if db.scalar(stmt.limit(1)):
        raise BizException(R.ASSET_CODE_DUPLICATE, "该父件的版本号已存在")


def activate_bom(db: Session, bom: Bom) -> None:
    """生效 BOM：同一父件的其它生效版本自动转「已作废」。"""
    others = db.scalars(
        select(Bom).where(
            Bom.parent_item_id == bom.parent_item_id,
            Bom.id != bom.id,
            Bom.status == "effective",
            Bom.deleted == 0,
        )
    ).all()
    for other in others:
        other.status = "obsolete"
        other.update_time = datetime.now()


def effective_bom_map(db: Session, parent_item_ids: list[int]) -> dict[int, Bom]:
    """父件 → 生效中的 BOM（多级展开用）。"""
    if not parent_item_ids:
        return {}
    rows = db.scalars(
        select(Bom).where(
            Bom.parent_item_id.in_(parent_item_ids),
            Bom.status == "effective",
            Bom.deleted == 0,
        )
    ).all()
    return {b.parent_item_id: b for b in rows}


def bom_explode(db: Session, bom: Bom, max_depth: int = 5) -> list[dict]:
    """多级 BOM 展开（子件本身是总成时继续下钻），带循环检测。"""
    lines = list(bom.lines or [])
    effective = effective_bom_map(db, [ln.item_id for ln in lines if ln.item_id])

    def build(line, level: int, chain: tuple[int, ...]) -> dict:
        node = {
            "itemId": line.item_id,
            "itemCode": line.item_code or "",
            "itemName": line.item_name or "",
            "spec": line.spec or "",
            "unit": line.unit or "",
            "qty": float(line.qty or 0),
            "lossRate": float(line.loss_rate or 0),
            "requiredQty": bom_line_qty(line),
            "refDesignator": line.ref_designator or "",
            "position": line.position or "",
            "level": level,
            "children": [],
        }
        child_bom = effective.get(line.item_id) if line.item_id else None
        if child_bom and level < max_depth and child_bom.id not in chain:
            for child in child_bom.lines or []:
                node["children"].append(build(child, level + 1, chain + (child_bom.id,)))
        return node

    return [build(ln, 1, (bom.id,)) for ln in lines]


def bom_usage(db: Session, bom: Bom, parent_qty: float = 1.0) -> list[dict]:
    """用量对比：按父件数量折算的理论需求 vs 该子件的历史实际领用（出库累计）。"""
    lines = list(bom.lines or [])
    item_ids = [ln.item_id for ln in lines if ln.item_id]
    out_map: dict[int, float] = {}
    if item_ids:
        rows = db.execute(
            select(StockLedger.item_id, func.coalesce(func.sum(StockLedger.quantity), 0))
            .where(
                StockLedger.item_id.in_(item_ids),
                StockLedger.deleted == 0,
                StockLedger.direction == "out",
            )
            .group_by(StockLedger.item_id)
        ).all()
        out_map = {item_id: float(qty) for item_id, qty in rows}
    result = []
    for ln in lines:
        required = round(bom_line_qty(ln) * parent_qty, 4)
        actual = round(out_map.get(ln.item_id, 0.0), 2) if ln.item_id else 0.0
        result.append(
            {
                "itemId": ln.item_id,
                "itemCode": ln.item_code or "",
                "itemName": ln.item_name or "",
                "spec": ln.spec or "",
                "unit": ln.unit or "",
                "unitQty": float(ln.qty or 0),
                "lossRate": float(ln.loss_rate or 0),
                "requiredQty": required,
                "actualOutQty": actual,
                "diffQty": round(actual - required, 4),
                "refDesignator": ln.ref_designator or "",
                "position": ln.position or "",
            }
        )
    return result


# ---------------- 到货验收（人工直通 / 审批通过共用） ----------------


def accept_receipt(db: Session, r: Receipt, operator) -> str:
    """验收确认：合格数量写入库存台账并回写库位在库数量。

    人工直通（``/receipts/{id}/accept``）与审批通过（流程 on_approved 钩子）
    共用同一段逻辑，保证"审批通过的验收"与"人工验收"产生的库存流水完全一致。

    Returns:
        验收后的状态：accepted（全合格）/ partial（部分合格）/ rejected（不合格）
    """
    total = 0.0
    qualified = 0.0
    for line in [i for i in (r.items or []) if not i.deleted]:
        total += float(line.quantity or 0)
        qualified += float(line.qualified_qty or 0)
        if float(line.qualified_qty or 0) <= 0:
            continue
        write_ledger(
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
            unit_price=float(line.price) if line.price is not None else None,
            reason="receipt",
            biz_type="receipt",
            biz_id=r.id,
            biz_no=r.receipt_no,
            operator_id=getattr(operator, "id", 0) or 0,
            operator_name=getattr(operator, "name", "") or getattr(operator, "username", "") or "",
            dept_id=getattr(operator, "dept_id", None),
            dept_name=getattr(operator, "dept_name", "") or "",
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
    r.version = (r.version or 0) + 1
    r.update_by = getattr(operator, "id", 0) or 0
    r.update_time = datetime.now()
    db.flush()
    return r.status
