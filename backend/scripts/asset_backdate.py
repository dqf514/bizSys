"""资产域演示数据回填：时间线 + PO/YS/PD/CZ/LY/LJ 重排 + 冗余/审计同步。"""
from __future__ import annotations

import json

from sqlalchemy import text

from app.core.db import SessionLocal

db = SessionLocal()
try:
    def upd(table, where_id, **cols):
        sets = ", ".join(f"{k}=:v_{k}" for k in cols)
        params = {f"v_{k}": v for k, v in cols.items()}
        params["i"] = where_id
        db.execute(text(f"UPDATE {table} SET {sets} WHERE id=:i"), params)

    # ---------- 1. 仓库/库位/物料 ----------
    wh = db.execute(text("SELECT id FROM ast_warehouse WHERE code='WH01' AND deleted=0")).scalar()
    upd("ast_warehouse", wh, create_time="2026-11-03 09:30", update_time="2026-11-03 09:30", create_by=1)
    locs = db.execute(text("SELECT id, code FROM ast_location WHERE deleted=0 ORDER BY id")).fetchall()
    loc_t = {"A-01-01": "2026-11-03 09:40", "A-02-01": "2026-11-03 09:50", "B-01-01": "2026-11-03 10:00"}
    for l in locs:
        t = loc_t.get(l.code)
        if t:
            upd("ast_location", l.id, create_time=t, update_time=t, create_by=1)
    items = db.execute(text("SELECT id, code FROM ast_item WHERE deleted=0 ORDER BY id")).fetchall()
    item_t = {"WP-001": "2026-11-03 10:20", "GS-001": "2026-11-03 10:35",
              "HO-001": "2026-11-03 10:50", "CC-001": "2026-11-03 11:05"}
    for it in items:
        t = item_t.get(it.code)
        if t:
            upd("ast_item", it.id, create_time=t, update_time=t, create_by=1)

    # ---------- 2. 台账（手工入/验收入/盘亏出） ----------
    led = {1: ("2026-11-05 10:15", "2026-11-05"),      # 手工入 液压油
           2: ("2026-11-09 15:30", "2026-11-09"),      # 验收入
           3: ("2026-11-09 15:30", "2026-11-09"),
           4: ("2026-11-12 15:40", "2026-11-12")}      # 盘亏出
    for lid, (t, h) in led.items():
        upd("ast_ledger", lid, create_time=t, update_time=t, happen_at=h, create_by=1)

    # ---------- 3. 采购订单 / 验收 ----------
    po = db.execute(text("SELECT id, create_time FROM ast_purchase_order WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_purchase_order", po, create_time="2026-11-05 14:20", update_time="2026-11-05 15:10", create_by=1)
    db.execute(text("UPDATE ast_purchase_order_item SET create_time='2026-11-05 14:20', update_time='2026-11-05 14:20', create_by=1 WHERE order_id=:i"), {"i": po})
    rc = db.execute(text("SELECT id FROM ast_receipt WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_receipt", rc, create_time="2026-11-09 09:45", update_time="2026-11-09 15:30", create_by=1)
    db.execute(text("UPDATE ast_receipt_item SET create_time='2026-11-09 09:45', update_time='2026-11-09 09:45', create_by=1 WHERE receipt_id=:i"), {"i": rc})

    # ---------- 4. 盘点 ----------
    cnt = db.execute(text("SELECT id FROM ast_count WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_count", cnt, create_time="2026-11-12 10:00", update_time="2026-11-12 15:40", create_by=1)
    db.execute(text("UPDATE ast_count_item SET create_time='2026-11-12 10:00', update_time='2026-11-12 10:00', create_by=1 WHERE count_id=:i"), {"i": cnt})

    # ---------- 5. 资产 + 折旧 ----------
    asset_t = {"FA-2024-017": "2026-11-03 14:00", "FA-2025-008": "2026-11-03 14:20", "FA-2019-002": "2026-11-03 14:40"}
    aids = {}
    for a in db.execute(text("SELECT id, asset_no FROM ast_asset WHERE deleted=0")).fetchall():
        aids[a.asset_no] = a.id
        t = asset_t.get(a.asset_no)
        if t:
            upd("ast_asset", a.id, create_time=t, update_time=t, create_by=1)
    dep_t = {("FA-2024-017", "2026-09"): ("2026-09-30 16:10", "2026-09-30"),
             ("FA-2024-017", "2026-10"): ("2026-10-30 16:10", "2026-10-30"),
             ("FA-2025-008", "2026-10"): ("2026-10-30 16:20", "2026-10-30"),
             ("FA-2019-002", "2026-10"): ("2026-10-30 16:30", "2026-10-30")}
    for d in db.execute(text("SELECT id, asset_no, period FROM ast_depreciation WHERE deleted=0")).fetchall():
        t = dep_t.get((d.asset_no, d.period))
        if t:
            upd("ast_depreciation", d.id, create_time=t[0], update_time=t[0], happen_at=t[1], create_by=1)

    # ---------- 6. 处置 ----------
    disp = db.execute(text("SELECT id FROM ast_disposal WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_disposal", disp, create_time="2026-11-13 09:40", update_time="2026-11-13 15:20",
        approve_at="2026-11-13 11:10", create_by=1)

    # ---------- 7. 工具/样件 + 借领 ----------
    tool = db.execute(text("SELECT id FROM ast_tool WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_tool", tool, create_time="2026-11-04 10:10", update_time="2026-11-04 10:10", create_by=1)
    tl = db.execute(text("SELECT id FROM ast_tool_loan WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_tool_loan", tl, create_time="2026-11-06 10:30", update_time="2026-11-06 10:30", create_by=1)
    proto = db.execute(text("SELECT id FROM ast_prototype WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_prototype", proto, create_time="2026-11-04 11:00", update_time="2026-11-04 11:00", create_by=1)
    pl = db.execute(text("SELECT id FROM ast_prototype_loan WHERE deleted=0 ORDER BY id LIMIT 1")).scalar()
    upd("ast_prototype_loan", pl, create_time="2026-11-05 14:00", update_time="2026-11-05 14:00", create_by=1)

    # ---------- 8. 审计映射（module='asset'，今日） ----------
    ENT = {}  # (action, biz_id) -> time，按实体时间回填
    ENT.update({("warehouse_create", wh): "2026-11-03 09:30"})
    for l in locs:
        if l.code in loc_t:
            ENT[("location_create", l.id)] = loc_t[l.code]
    for it in items:
        if it.code in item_t:
            ENT[("item_create", it.id)] = item_t[it.code]
    ENT[("ledger_create", 1)] = "2026-11-05 10:15"
    ENT[("ledger_create", 2)] = "2026-11-09 15:30"
    ENT[("ledger_create", 3)] = "2026-11-09 15:30"
    ENT[("ledger_create", 4)] = "2026-11-12 15:40"
    ENT[("purchase_order_create", po)] = "2026-11-05 14:20"
    ENT[("purchase_order_confirm", po)] = "2026-11-05 15:10"
    ENT[("receipt_create", rc)] = "2026-11-09 09:45"
    ENT[("receipt_accept", rc)] = "2026-11-09 15:30"
    ENT[("count_create", cnt)] = "2026-11-12 10:00"
    ENT[("count_start", cnt)] = "2026-11-12 10:30"
    ENT[("count_finish", cnt)] = "2026-11-12 15:40"
    for no, t in asset_t.items():
        ENT[("asset_create", aids[no])] = t
    ENT[("disposal_create", disp)] = "2026-11-13 09:40"
    ENT[("disposal_approve", disp)] = "2026-11-13 11:10"
    ENT[("disposal_complete", disp)] = "2026-11-13 15:20"
    ENT[("tool_create", tool)] = "2026-11-04 10:10"
    ENT[("tool_loan_create", tl)] = "2026-11-06 10:30"
    ENT[("prototype_create", proto)] = "2026-11-04 11:00"
    ENT[("prototype_loan_create", pl)] = "2026-11-05 14:00"
    dep_audit_t = {("FA-2024-017", "2026-09"): "2026-09-30 16:10",
                   ("FA-2024-017", "2026-10"): "2026-10-30 16:10",
                   ("FA-2025-008", "2026-10"): "2026-10-30 16:20",
                   ("FA-2019-002", "2026-10"): "2026-10-30 16:30"}
    rows = db.execute(text("""SELECT id, action, biz_id, detail FROM sys_audit_log
                              WHERE module='asset' AND create_time >= '2026-11-21'""")).fetchall()
    fixed = unmapped = 0
    un = []
    for r in rows:
        t = ENT.get((r.action, r.biz_id))
        if t is None and r.action == "asset_depreciate" and r.detail:
            try:
                d = json.loads(r.detail)
                t = dep_audit_t.get((d.get("assetNo"), d.get("period")))
            except Exception:
                pass
        if t:
            db.execute(text("UPDATE sys_audit_log SET create_time=:t WHERE id=:id"), {"t": t, "id": r.id})
            fixed += 1
        else:
            unmapped += 1
            un.append((r.id, r.action, r.biz_id))
    print(f"审计映射 {fixed} 行；未映射 {unmapped}: {un}")

    # ---------- 9. 重排单号（按 create_time 日期） ----------
    def renumber(table, col, prefix):
        rows2 = db.execute(text(
            f"SELECT id, create_time AS d FROM {table} WHERE deleted=0 AND {col}<>'' ORDER BY create_time, id")).fetchall()
        seq: dict[str, int] = {}
        mapping = {}
        for r in rows2:
            key = r.d.strftime("%Y%m%d")
            seq[key] = seq.get(key, 0) + 1
            new = f"{prefix}{key}{seq[key]:04d}"
            old = db.execute(text(f"SELECT {col} FROM {table} WHERE id=:i"), {"i": r.id}).scalar()
            if old != new:
                mapping[old] = new
                db.execute(text(f"UPDATE {table} SET {col}=:n WHERE id=:i"), {"n": new, "i": r.id})
        return mapping

    m_po = renumber("ast_purchase_order", "order_no", "PO")
    m_ys = renumber("ast_receipt", "receipt_no", "YS")
    m_pd = renumber("ast_count", "count_no", "PD")
    m_cz = renumber("ast_disposal", "disposal_no", "CZ")
    m_ly = renumber("ast_tool_loan", "loan_no", "LY")
    m_lj = renumber("ast_prototype_loan", "loan_no", "LJ")
    print("重排:", {**m_po, **m_ys, **m_pd, **m_cz, **m_ly, **m_lj})

    # 冗余同步：验收单.order_no、台账.biz_no、审计 detail
    po_no = db.execute(text("SELECT order_no FROM ast_purchase_order WHERE id=:i"), {"i": po}).scalar()
    db.execute(text("UPDATE ast_receipt SET order_no=:n WHERE id=:i"), {"n": po_no, "i": rc})
    all_map = {**m_po, **m_ys, **m_pd, **m_cz, **m_ly, **m_lj}
    for old, new in all_map.items():
        db.execute(text("""UPDATE ast_ledger SET biz_no=REPLACE(biz_no,:o,:n)
                           WHERE biz_no IS NOT NULL AND biz_no LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE sys_audit_log SET detail=REPLACE(detail,:o,:n)
                           WHERE detail IS NOT NULL AND detail LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
    db.commit()

    # ---------- 10. 校验 ----------
    bad = db.execute(text("""SELECT COUNT(*) FROM (
        SELECT create_time FROM ast_warehouse UNION ALL SELECT create_time FROM ast_item
        UNION ALL SELECT create_time FROM ast_purchase_order UNION ALL SELECT create_time FROM ast_receipt
        UNION ALL SELECT create_time FROM ast_count UNION ALL SELECT create_time FROM ast_asset
        UNION ALL SELECT create_time FROM ast_disposal UNION ALL SELECT create_time FROM ast_tool_loan
        UNION ALL SELECT create_time FROM ast_prototype_loan UNION ALL SELECT create_time FROM ast_ledger) t
        WHERE HOUR(create_time)<8 OR HOUR(create_time)>=20""")).scalar()
    left = db.execute(text("""SELECT COUNT(*) FROM sys_audit_log
                              WHERE module='asset' AND create_time >= '2026-11-21'""")).scalar()
    print("工时越界(应0):", bad, "| 今日资产审计遗留(应0):", left)
    for t_, c_ in (("ast_purchase_order", "order_no"), ("ast_receipt", "receipt_no"), ("ast_count", "count_no"),
                   ("ast_disposal", "disposal_no"), ("ast_tool_loan", "loan_no"), ("ast_prototype_loan", "loan_no")):
        vals = [x[0] for x in db.execute(text(f"SELECT {c_} FROM {t_} WHERE deleted=0")).fetchall()]
        print(f"  {t_}: {vals}")
finally:
    db.close()
print("ASSET_BACKDATE_DONE")
