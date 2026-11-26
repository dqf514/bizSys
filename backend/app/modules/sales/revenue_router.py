"""营收分析看板路由 /api/v1/sales/revenue（B7 · CSV 第 3 项）。

按 **业务线 / 客户 / 合同 / 期间** 四个维度做营收分析，并给出三口径说明。
业务规则集中在本文件（与前端 `src/modules/sales/pages/RevenueBoard.vue` 同一份口径）。

================ 口径定义（写死，前后端同一份） ================

1. **合同额** = 已审批通过合同（`ctr_contract.status = 'approved'`）的 `amount` 合计。
   - 排除：`deleted != 0` 的行；`draft` / `approving` / `rejected` / `voided` 状态。
   - **归期（签订日期）**：合同表**没有** `sign_date` 列 —— 取 `start_date`（合同起始日），
     为空回落 `create_time` 当日（合同建立日）。归期落在 `[from, to]` 闭区间内才计入。

2. **结算额** = **客户已确认**的结算单（`fin_settlement.amount`）合计。
   - 状态口径：`status ∈ {pending, invoicing, invoiced, paid}` **且**
     （`confirm_status = 'confirmed'` **或** `status ∈ {invoicing, invoiced, paid}`）。
     进入开票环节的单据必然已由客户确认。
   - 排除：`deleted != 0`；`approving`（结算审批中，未生效）；`rejected`（已驳回）；
     `pending` 且客户未确认（`confirm_status ∈ {'', 'pending', 'objected'}`）的结算单。
   - **归期（结算日期）**：结算单**没有**日期列 —— 取 `create_time` 当日（结算单建立日）。
     归期落在 `[from, to]` 闭区间内才计入。

3. **回款额** = 已确认到账的回款单（`fin_payment.status = 'confirmed'`）的 `amount` 合计。
   - 排除：`deleted != 0`；`draft`（待复核）/ `approving`（复核中）/ `rejected`（已驳回）。
   - **归期（收款日期）**：`fin_payment.paid_at`（到账日期），落在 `[from, to]` 闭区间内才计入。

4. **业务线（biz_block）不在合同上** —— 合同表与结算单都没有该列，只有 `task_task.biz_block`。
   归类规则（统一适用三条流，保证同一笔业务在三个口径里落到同一个桶）：
   - 合同：取其关联任务（`task_task.contract_id`）的 `biz_block` 去重集合；
     恰好 1 个 → 该业务线；多个 → `multi`（混合）；0 个 → 回落其结算单所挂任务的
     `biz_block`；仍无 → `unknown`（未分类）。
   - 结算单：先看其合同（用上面的合同归类），无合同时看其任务（`settlement.task_id`）的
     `biz_block`，都没有 → `unknown`。
   - 回款单：沿其结算单归类。
   - 字典 `biz_block` 取值见 `app/seeds/init_data.py`（consulting_dept / model_center /
     windtunnel_dept / cfd），**不臆造**。

5. **客户维度**：合同的 `customer_id`；结算单取自身 `customer_id`（为空时回落到合同的
   `customer_id`）；回款单沿其结算单。客户筛选条件同时作用在三条流上。

6. **派生指标**：
   - `unsettledAmount` = contractAmount − settledAmount（已签未结算）
   - `unreceivedAmount` = settledAmount − receivedAmount（已结算未回款）
   - `collectionRate`（结算率 %）= settledAmount / contractAmount × 100
   - `receivableRate`（回款率 %）= receivedAmount / settledAmount × 100
   - 除数为 0 时返回 0。

7. **期间缺省**：最近 12 个自然月（`to` = 今天，`from` = 今天所在月往前推 11 个月的 1 号）。

无对应数据时返回 0 与空数组，不报错。
"""

from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.common.audit import record as audit
from app.core import response as R
from app.core.db import get_db
from app.core.deps import require_perm
from app.core.exceptions import BizException
from app.core.route import EnvelopeRoute
from app.modules.auth.models import User
from app.modules.contract.models import Contract
from app.modules.finance.models import Payment, Settlement
from app.modules.task.models import Task
from app.services.excel import export_xlsx_styled, now_filename

router = APIRouter(prefix="/sales", tags=["sales"], route_class=EnvelopeRoute)

# ---------------- 状态口径 ----------------

#: 计入合同额的状态（已审批通过 = 已签订）
CONTRACT_STATUS_IN = ("approved",)
#: 计入结算额的状态（排除审批中 / 已驳回）
SETTLEMENT_STATUS_IN = ("pending", "invoicing", "invoiced", "paid")
#: 客户已确认的结算单状态（进入开票环节必然已确认客户）
SETTLEMENT_CONFIRMED_STATUS_IN = ("invoicing", "invoiced", "paid")
#: 计入回款额的状态（已确认到账；排除待复核 / 复核中 / 已驳回）
PAYMENT_STATUS_IN = ("confirmed",)

#: 业务线兜底桶（合同下无任务 / 无任何业务线信息）
BIZ_UNKNOWN = "unknown"
#: 业务线混合桶（同一合同下任务跨多个业务线）
BIZ_MULTI = "multi"

PERM = "sales:revenue:view"

CALIBER = {
    "contractAmount": "已签合同金额合计（已审批通过合同，按合同签订日期归期）",
    "settledAmount": "客户已确认结算单金额合计（已确认且未驳回的结算单，按结算单建立日期归期）",
    "receivedAmount": "已确认回款金额合计（已确认到账回款单，按到账日期归期）",
}

#: 口径说明的英文版（前端按 locale 切换；中文版是权威口径）
CALIBER_EN = {
    "contractAmount": "Sum of signed contract amounts (approved contracts, bucketed by contract sign date)",
    "settledAmount": (
        "Sum of customer-confirmed settlement amounts "
        "(confirmed and not rejected settlements, bucketed by settlement creation date)"
    ),
    "receivedAmount": "Sum of confirmed receipts (payments confirmed as received, bucketed by receipt date)",
}

EXPORT_COLS = [
    {"key": "customerName", "label": "客户", "width": 28},
    {"key": "contractAmount", "label": "合同额(元)", "width": 16},
    {"key": "settledAmount", "label": "结算额(元)", "width": 16},
    {"key": "receivedAmount", "label": "回款额(元)", "width": 16},
    {"key": "unsettledAmount", "label": "已签未结算(元)", "width": 16},
    {"key": "unreceivedAmount", "label": "已结算未回款(元)", "width": 18},
    {"key": "contractCount", "label": "合同数", "width": 10},
    {"key": "bizBlocks", "label": "业务线", "width": 24},
    {"key": "collectionRate", "label": "结算率(%)", "width": 12},
    {"key": "receivableRate", "label": "回款率(%)", "width": 12},
]


# ---------------- 小工具 ----------------


def _d(v) -> str:
    if hasattr(v, "strftime"):
        return v.strftime("%Y-%m-%d")
    return v or ""


def _f(v) -> float:
    if v is None:
        return 0.0
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _r(v: float) -> float:
    """金额保留 2 位小数。"""
    return round(v + 1e-9, 2)


def _pct(part: float, whole: float) -> float:
    """比率（%），分母为 0 时返回 0。"""
    if not whole:
        return 0.0
    return round(part / whole * 100, 1)


def _month(d) -> str:
    return d.strftime("%Y-%m") if d else ""


def _default_range() -> tuple[date, date]:
    """缺省期间 = 最近 12 个自然月（含今天所在月）。"""
    today = date.today()
    y, m = today.year, today.month - 11
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1), today


def _parse_date(raw: str | None, fallback: date) -> date:
    if not raw:
        return fallback
    try:
        return datetime.strptime(raw.strip()[:10], "%Y-%m-%d").date()
    except ValueError as exc:
        raise BizException(R.SALES_REVENUE_INVALID_STATE, f"非法日期：{raw}") from exc


def _dict_labels(db: Session) -> dict[str, tuple[str, str]]:
    """biz_block 字典 → {value: (中文标签, 英文标签)}。"""
    from app.modules.admin.models import DictItem

    rows = db.execute(
        select(DictItem.value, DictItem.label, DictItem.label_en).where(
            DictItem.dict_type_code == "biz_block",
            DictItem.status == "enabled",
            DictItem.deleted == 0,
        )
    ).all()
    return {r[0]: (r[1] or r[0], r[2] or r[1] or r[0]) for r in rows}


# ---------------- 取数 ----------------


def _load_contracts(db: Session, from_date: date, to_date: date, customer_id: int | None) -> list[dict]:
    """期间内已审批通过合同。归期列 = coalesce(start_date, date(create_time))。"""
    sign = func.coalesce(Contract.start_date, func.date(Contract.create_time))
    stmt = select(
        Contract.id,
        Contract.contract_no,
        Contract.name,
        Contract.customer_id,
        Contract.customer_name,
        Contract.amount,
        Contract.start_date,
        Contract.create_time,
    ).where(
        Contract.deleted == 0,
        Contract.status.in_(CONTRACT_STATUS_IN),
        sign >= from_date,
        sign <= to_date,
    )
    if customer_id is not None:
        stmt = stmt.where(Contract.customer_id == customer_id)
    out = []
    for r in db.execute(stmt).all():
        sign_date = r.start_date or (r.create_time.date() if r.create_time else None)
        if sign_date is None or not (from_date <= sign_date <= to_date):
            continue
        out.append(
            {
                "id": r.id,
                "contractNo": r.contract_no or "",
                "name": r.name or "",
                "customerId": r.customer_id,
                "customerName": r.customer_name or "",
                "amount": _f(r.amount),
                "signDate": sign_date,
            }
        )
    return out


def _load_settlements(db: Session, from_date: date, to_date: date) -> list[dict]:
    """期间内**客户已确认**的结算单。归期列 = date(create_time)。

    口径：`status IN (pending, invoicing, invoiced, paid)` 且
    （`confirm_status = 'confirmed'` 或 `status IN (invoicing, invoiced, paid)`）。
    —— pending 且客户未确认 / 有异议（objected）的结算单**不计入**结算额。
    """
    sdate = func.date(Settlement.create_time)
    stmt = select(
        Settlement.id,
        Settlement.contract_id,
        Settlement.customer_id,
        Settlement.task_id,
        Settlement.amount,
        Settlement.create_time,
    ).where(
        Settlement.deleted == 0,
        Settlement.status.in_(SETTLEMENT_STATUS_IN),
        or_(
            Settlement.confirm_status == "confirmed",
            Settlement.status.in_(SETTLEMENT_CONFIRMED_STATUS_IN),
        ),
        sdate >= from_date,
        sdate <= to_date,
    )
    out = []
    for r in db.execute(stmt).all():
        d = r.create_time.date() if r.create_time else None
        if d is None or not (from_date <= d <= to_date):
            continue
        out.append(
            {
                "id": r.id,
                "contractId": r.contract_id,
                "customerId": r.customer_id,
                "taskId": r.task_id,
                "amount": _f(r.amount),
                "date": d,
            }
        )
    return out


def _load_payments(db: Session, from_date: date, to_date: date) -> list[dict]:
    """期间内已确认到账回款单。归期列 = paid_at。"""
    stmt = select(
        Payment.id,
        Payment.settlement_id,
        Payment.amount,
        Payment.paid_at,
    ).where(
        Payment.deleted == 0,
        Payment.status.in_(PAYMENT_STATUS_IN),
        Payment.paid_at >= from_date,
        Payment.paid_at <= to_date,
    )
    return [
        {"id": r.id, "settlementId": r.settlement_id, "amount": _f(r.amount), "date": r.paid_at}
        for r in db.execute(stmt).all()
    ]


def _load_settlements_by_id(db: Session, ids: set[int]) -> dict[int, dict]:
    """按 id 取结算单的归属信息（回款单可能关联期间外的结算单）。"""
    if not ids:
        return {}
    rows = db.execute(
        select(Settlement.id, Settlement.contract_id, Settlement.customer_id, Settlement.task_id).where(
            Settlement.id.in_(ids)
        )
    ).all()
    return {r[0]: {"contractId": r[1], "customerId": r[2], "taskId": r[3]} for r in rows}


def _load_task_blocks(db: Session) -> dict[int, set[str]]:
    """contract_id → 该合同下任务的 biz_block 去重集合。"""
    pairs = db.execute(
        select(Task.contract_id, Task.biz_block).where(
            Task.deleted == 0,
            Task.contract_id.is_not(None),
            Task.biz_block != "",
        )
    ).all()
    out: dict[int, set[str]] = {}
    for cid, block in pairs:
        out.setdefault(cid, set()).add(block)
    return out


def _load_task_block_by_id(db: Session, ids: set[int]) -> dict[int, str]:
    """task_id → biz_block。"""
    if not ids:
        return {}
    rows = db.execute(select(Task.id, Task.biz_block).where(Task.deleted == 0, Task.id.in_(ids))).all()
    return {r[0]: r[1] or "" for r in rows}


def _load_contract_blocks_from_settlements(db: Session) -> dict[int, set[str]]:
    """合同下没有任务时，用其结算单所挂任务的 biz_block 回落。"""
    pairs = db.execute(
        select(Settlement.contract_id, Settlement.task_id).where(
            Settlement.deleted == 0,
            Settlement.contract_id.is_not(None),
            Settlement.task_id.is_not(None),
        )
    ).all()
    task_ids = {t for _, t in pairs}
    tmap = _load_task_block_by_id(db, task_ids)
    out: dict[int, set[str]] = {}
    for cid, tid in pairs:
        block = tmap.get(tid, "")
        if block:
            out.setdefault(cid, set()).add(block)
    return out


# ---------------- 归类 ----------------


def _contract_block(contract_id: int | None, task_map: dict[int, set[str]], settle_map: dict[int, set[str]]) -> str:
    """合同 → 业务线（任务集合去重；多值 multi；无值 unknown）。"""
    if contract_id is None:
        return BIZ_UNKNOWN
    blocks = task_map.get(contract_id) or set()
    if not blocks:
        blocks = settle_map.get(contract_id) or set()
    if not blocks:
        return BIZ_UNKNOWN
    if len(blocks) == 1:
        return next(iter(blocks))
    return BIZ_MULTI


def _block_text(block: str, labels: dict[str, tuple[str, str]]) -> str:
    zh, _en = labels.get(block, (block, block))
    return zh


# ---------------- 看板 ----------------


def _build_board(
    db: Session,
    from_date: date,
    to_date: date,
    biz_block: str | None,
    customer_id: int | None,
) -> dict:
    labels = _dict_labels(db)

    contracts = _load_contracts(db, from_date, to_date, customer_id)
    settlements = _load_settlements(db, from_date, to_date)
    payments = _load_payments(db, from_date, to_date)

    task_map = _load_task_blocks(db)
    settle_map = _load_contract_blocks_from_settlements(db)
    task_blocks = _load_task_block_by_id(db, {s["taskId"] for s in settlements if s.get("taskId")})

    # 合同 → 业务线（缓存；覆盖期间内合同与结算单引用的合同）
    contract_block_cache: dict[int, str] = {}

    def block_of_contract(cid: int | None) -> str:
        if cid is None:
            return BIZ_UNKNOWN
        if cid not in contract_block_cache:
            contract_block_cache[cid] = _contract_block(cid, task_map, settle_map)
        return contract_block_cache[cid]

    contract_customer: dict[int, int] = {c["id"]: c["customerId"] for c in contracts}

    # 结算单 → 业务线 / 客户
    for s in settlements:
        cid = s.get("contractId")
        if cid is not None:
            s["block"] = block_of_contract(cid)
            if s.get("customerId") is None:
                s["customerId"] = contract_customer.get(cid)
        else:
            s["block"] = task_blocks.get(s.get("taskId"), "") or BIZ_UNKNOWN

    # 回款单 → 结算单 → 业务线 / 客户
    pay_settlements = _load_settlements_by_id(db, {p["settlementId"] for p in payments if p.get("settlementId")})
    settlement_index = {s["id"]: s for s in settlements}
    for p in payments:
        sid = p.get("settlementId")
        linked = settlement_index.get(sid)
        if linked is not None:
            p["block"] = linked["block"]
            p["customerId"] = linked.get("customerId")
            p["contractId"] = linked.get("contractId")
        else:
            ref = pay_settlements.get(sid) or {}
            p["contractId"] = ref.get("contractId")
            p["customerId"] = ref.get("customerId")
            p["block"] = block_of_contract(ref.get("contractId")) if ref.get("contractId") else (
                task_blocks.get(ref.get("taskId"), "") or BIZ_UNKNOWN
            )

    # 业务线筛选（作用在三条流上）
    if biz_block:
        contracts = [c for c in contracts if block_of_contract(c["id"]) == biz_block]
        settlements = [s for s in settlements if s["block"] == biz_block]
        payments = [p for p in payments if p.get("block") == biz_block]

    # ---- 汇总 ----
    total_contract = sum(c["amount"] for c in contracts)
    total_settled = sum(s["amount"] for s in settlements)
    total_received = sum(p["amount"] for p in payments)
    customer_ids = {c["customerId"] for c in contracts if c.get("customerId") is not None}
    customer_ids |= {s["customerId"] for s in settlements if s.get("customerId") is not None}
    customer_ids |= {p["customerId"] for p in payments if p.get("customerId") is not None}

    summary = {
        "contractAmount": _r(total_contract),
        "settledAmount": _r(total_settled),
        "receivedAmount": _r(total_received),
        "unsettledAmount": _r(total_contract - total_settled),
        "unreceivedAmount": _r(total_settled - total_received),
        "contractCount": len(contracts),
        "customerCount": len(customer_ids),
        "avgContractAmount": _r(total_contract / len(contracts)) if contracts else 0.0,
        "receivableRate": _pct(total_received, total_settled),
        "collectionRate": _pct(total_settled, total_contract),
    }

    # ---- 按业务线 ----
    by_block: dict[str, dict] = {}

    def block_acc(key: str) -> dict:
        return by_block.setdefault(
            key,
            {
                "contractAmount": 0.0,
                "settledAmount": 0.0,
                "receivedAmount": 0.0,
                "contractCount": 0,
                "customers": set(),
            },
        )

    for c in contracts:
        acc = block_acc(block_of_contract(c["id"]))
        acc["contractAmount"] += c["amount"]
        acc["contractCount"] += 1
        if c.get("customerId") is not None:
            acc["customers"].add(c["customerId"])
    for s in settlements:
        block_acc(s["block"])["settledAmount"] += s["amount"]
    for p in payments:
        block_acc(p.get("block") or BIZ_UNKNOWN)["receivedAmount"] += p["amount"]

    by_biz_block = []
    for key, acc in by_block.items():
        zh, en = labels.get(key, (key, key))
        by_biz_block.append(
            {
                "bizBlock": key,
                "bizBlockText": zh,
                "bizBlockTextEn": en,
                "contractAmount": _r(acc["contractAmount"]),
                "settledAmount": _r(acc["settledAmount"]),
                "receivedAmount": _r(acc["receivedAmount"]),
                "contractCount": acc["contractCount"],
                "customerCount": len(acc["customers"]),
                "collectionRate": _pct(acc["settledAmount"], acc["contractAmount"]),
                "receivableRate": _pct(acc["receivedAmount"], acc["settledAmount"]),
            }
        )
    by_biz_block.sort(key=lambda x: -x["contractAmount"])

    # ---- 按客户 ----
    by_customer: dict[int, dict] = {}

    def cust_acc(cid) -> dict:
        return by_customer.setdefault(
            cid,
            {
                "customerName": "",
                "contractAmount": 0.0,
                "settledAmount": 0.0,
                "receivedAmount": 0.0,
                "contractCount": 0,
                "blocks": set(),
            },
        )

    for c in contracts:
        if c.get("customerId") is None:
            continue
        acc = cust_acc(c["customerId"])
        if not acc["customerName"]:
            acc["customerName"] = c["customerName"]
        acc["contractAmount"] += c["amount"]
        acc["contractCount"] += 1
        acc["blocks"].add(block_of_contract(c["id"]))
    for s in settlements:
        if s.get("customerId") is None:
            continue
        acc = cust_acc(s["customerId"])
        acc["settledAmount"] += s["amount"]
        acc["blocks"].add(s["block"])
    for p in payments:
        if p.get("customerId") is None:
            continue
        acc = cust_acc(p["customerId"])
        acc["receivedAmount"] += p["amount"]
        acc["blocks"].add(p.get("block") or BIZ_UNKNOWN)

    by_customer_rows = []
    for cid, acc in by_customer.items():
        by_customer_rows.append(
            {
                "customerId": cid,
                "customerName": acc["customerName"],
                "contractAmount": _r(acc["contractAmount"]),
                "settledAmount": _r(acc["settledAmount"]),
                "receivedAmount": _r(acc["receivedAmount"]),
                "unsettledAmount": _r(acc["contractAmount"] - acc["settledAmount"]),
                "unreceivedAmount": _r(acc["settledAmount"] - acc["receivedAmount"]),
                "contractCount": acc["contractCount"],
                "bizBlocks": [_block_text(b, labels) for b in sorted(acc["blocks"])],
                "bizBlockCodes": sorted(acc["blocks"]),
                "collectionRate": _pct(acc["settledAmount"], acc["contractAmount"]),
                "receivableRate": _pct(acc["receivedAmount"], acc["settledAmount"]),
            }
        )
    by_customer_rows.sort(key=lambda x: -x["contractAmount"])

    # ---- 按月 ----
    by_month: dict[str, dict] = {}

    def month_acc(m: str) -> dict:
        return by_month.setdefault(
            m, {"contractAmount": 0.0, "settledAmount": 0.0, "receivedAmount": 0.0, "contractCount": 0}
        )

    for c in contracts:
        acc = month_acc(_month(c["signDate"]))
        acc["contractAmount"] += c["amount"]
        acc["contractCount"] += 1
    for s in settlements:
        month_acc(_month(s["date"]))["settledAmount"] += s["amount"]
    for p in payments:
        month_acc(_month(p["date"]))["receivedAmount"] += p["amount"]

    by_month_rows = []
    for m in sorted(by_month.keys()):
        acc = by_month[m]
        by_month_rows.append(
            {
                "month": m,
                "contractAmount": _r(acc["contractAmount"]),
                "settledAmount": _r(acc["settledAmount"]),
                "receivedAmount": _r(acc["receivedAmount"]),
                "contractCount": acc["contractCount"],
                "collectionRate": _pct(acc["settledAmount"], acc["contractAmount"]),
                "receivableRate": _pct(acc["receivedAmount"], acc["settledAmount"]),
            }
        )

    # ---- 按合同明细 ----
    contract_acc: dict[int, dict] = {}

    def c_acc(cid: int) -> dict:
        return contract_acc.setdefault(cid, {"settledAmount": 0.0, "receivedAmount": 0.0})

    for s in settlements:
        cid = s.get("contractId")
        if cid is None:
            continue
        c_acc(cid)["settledAmount"] += s["amount"]
    for p in payments:
        cid = p.get("contractId")
        if cid is None:
            continue
        c_acc(cid)["receivedAmount"] += p["amount"]

    by_contract_rows = []
    for c in contracts:
        acc = contract_acc.get(c["id"], {"settledAmount": 0.0, "receivedAmount": 0.0})
        block = block_of_contract(c["id"])
        zh, en = labels.get(block, (block, block))
        by_contract_rows.append(
            {
                "contractId": c["id"],
                "contractNo": c["contractNo"],
                "contractName": c["name"],
                "customerId": c["customerId"],
                "customerName": c["customerName"],
                "bizBlock": block,
                "bizBlockText": zh,
                "bizBlockTextEn": en,
                "amount": _r(c["amount"]),
                "contractAmount": _r(c["amount"]),
                "settledAmount": _r(acc["settledAmount"]),
                "receivedAmount": _r(acc["receivedAmount"]),
                "signDate": _d(c["signDate"]),
                "collectionRate": _pct(acc["settledAmount"], c["amount"]),
                "receivableRate": _pct(acc["receivedAmount"], acc["settledAmount"]),
            }
        )
    by_contract_rows.sort(key=lambda x: -x["amount"])

    return {
        "range": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "summary": summary,
        "byBizBlock": by_biz_block,
        "byCustomer": by_customer_rows,
        "byMonth": by_month_rows,
        "byContract": by_contract_rows,
        "caliber": dict(CALIBER),
        "caliberEn": dict(CALIBER_EN),
    }


# ---------------- 端点 ----------------


def _resolve_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    default_from, default_to = _default_range()
    from_date = _parse_date(date_from.isoformat() if date_from else None, default_from)
    to_date = _parse_date(date_to.isoformat() if date_to else None, default_to)
    if from_date > to_date:
        raise BizException(R.SALES_REVENUE_INVALID_STATE, "起始日期不能晚于截止日期")
    return from_date, to_date


@router.get("/revenue/board")
def revenue_board(
    date_from: date | None = Query(None, alias="from", description="起始日期（含）"),
    date_to: date | None = Query(None, alias="to", description="截止日期（含）"),
    biz_block: str | None = Query(None, max_length=32, description="业务线 biz_block"),
    customer_id: int | None = Query(None, description="客户 crm_customer.id"),
    _: User = Depends(require_perm(PERM)),
    db: Session = Depends(get_db),
):
    """营收分析看板：业务线 / 客户 / 合同 / 期间 四个维度。"""
    from_date, to_date = _resolve_range(date_from, date_to)
    return _build_board(db, from_date, to_date, biz_block or None, customer_id)


@router.get("/revenue/caliber")
def revenue_caliber(
    _: User = Depends(require_perm(PERM)),
):
    """口径说明（与 board 的 caliber 一致），供前端单独展示。"""
    return {"caliber": dict(CALIBER), "caliberEn": dict(CALIBER_EN)}


@router.get("/revenue/export")
def export_revenue(
    request: Request,
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    biz_block: str | None = Query(None, max_length=32),
    customer_id: int | None = Query(None),
    current: User = Depends(require_perm(PERM)),
    db: Session = Depends(get_db),
):
    """导出「按客户」明细（xlsx）。"""
    from_date, to_date = _resolve_range(date_from, date_to)
    board = _build_board(db, from_date, to_date, biz_block or None, customer_id)
    rows = []
    for r in board["byCustomer"]:
        row = dict(r)
        row["bizBlocks"] = "、".join(r.get("bizBlocks") or [])
        rows.append(row)
    payload = export_xlsx_styled(rows, EXPORT_COLS, "sales_revenue")
    audit(
        db,
        user_id=current.id,
        module="sales",
        action="revenue_export",
        detail={"count": len(rows), "from": from_date.isoformat(), "to": to_date.isoformat()},
        trace_id=getattr(request.state, "trace_id", ""),
    )
    db.commit()
    return Response(
        payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{now_filename('sales_revenue')}"},
    )


__all__ = [
    "router",
    "CALIBER",
    "CALIBER_EN",
    "CONTRACT_STATUS_IN",
    "SETTLEMENT_STATUS_IN",
    "SETTLEMENT_CONFIRMED_STATUS_IN",
    "PAYMENT_STATUS_IN",
]
