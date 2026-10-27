"""采购演示数据回填：时间线（工作日/工作时段）+ PR/CG/RK/CK 重排 + 冗余与审批快照同步。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.core.db import SessionLocal

D = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")  # noqa: E731

db = SessionLocal()
try:
    # ---------------- 供应商 ----------------
    sup_times = {
        52: "2026-09-08 09:20", 53: "2026-09-08 10:35", 54: "2026-09-09 09:40", 55: "2026-09-09 14:15",
        56: "2026-09-10 10:05", 57: "2026-09-10 15:30", 58: "2026-09-11 09:50", 59: "2026-09-11 14:40",
    }
    for cid, t in sup_times.items():
        db.execute(text("""UPDATE crm_customer SET create_time=:t, update_time=:t, create_by=1
                           WHERE id=:id AND partner_type='supplier'"""),
                   {"t": t, "id": cid})

    # ---------------- 申请时间线 ----------------
    # key: (create, mgr_action_or_None, leader_action_or_None)  None=该节点未到/未批
    REQ_TL = {
        "风洞应变片与力学传感器年度采购": ("2026-09-21 09:30", "2026-09-22 10:15", "2026-09-23 14:20"),
        "实验室标准气体与标准物质采购": ("2026-09-24 09:45", "2026-09-25 10:40", "2026-09-28 15:05"),
        "数据采集系统板卡扩容": ("2026-09-29 10:10", "2026-09-30 11:00", "2026-10-08 10:25"),
        "试验数据服务器与存储备件采购": ("2026-10-09 09:35", "2026-10-12 10:50", "2026-10-13 15:15"),
        "模型加工中心刀具耗材补货": ("2026-10-14 09:55", "2026-10-15 10:30", "2026-10-16 14:45"),
        "环境试验箱年度维保服务采购": ("2026-10-19 09:40", "2026-10-20 10:20", None),   # 等 leader（节点2待办）
        "风洞试验区照明系统LED改造": ("2026-10-21 09:25", None, None),                 # 等 manager（节点1待办）
        "办公区域工位家具更新": ("2026-10-22 11:10", None, None),                      # 草稿（未提交）
        "样品冷藏柜采购": ("2026-10-23 16:05", None, None),                            # 草稿
        "进口六分量天平采购": ("2026-10-12 09:50", "2026-10-13 11:25", None),          # manager 驳回
    }
    rows = db.execute(text("""SELECT id, title, status, flow_instance_id, create_time
                              FROM pur_request WHERE deleted=0""")).fetchall()
    req_ids = {}
    for r in rows:
        create, mgr, leader = REQ_TL[r.title]
        req_ids[r.title] = r.id
        last = leader or mgr or create
        db.execute(text("""UPDATE pur_request SET create_time=:c, update_time=:u, create_by=1 WHERE id=:id"""),
                   {"c": create, "u": last, "id": r.id})
        db.execute(text("UPDATE pur_request_item SET create_time=:c, update_time=:c WHERE request_id=:id"),
                   {"c": create, "id": r.id})
        if not r.flow_instance_id:
            continue
        iid = r.flow_instance_id
        db.execute(text("""UPDATE approval_instance SET create_time=:c, update_time=:u WHERE id=:iid"""),
                   {"c": create, "u": last, "iid": iid})
        rec_times = [create]
        if mgr:
            rec_times.append(mgr)
        if leader and r.status == "approved":
            rec_times.append(leader)
        recs = db.execute(text("SELECT id FROM approval_record WHERE instance_id=:i ORDER BY id"),
                          {"i": iid}).fetchall()
        for idx, rec in enumerate(recs):
            t = rec_times[idx] if idx < len(rec_times) else last
            db.execute(text("UPDATE approval_record SET create_time=:t, update_time=:t WHERE id=:id"),
                       {"t": t, "id": rec.id})
        # 任务：manager1(id=2)=节点1；leader1(id=3)=节点2（申请流）
        tasks = db.execute(text("""SELECT id, assignee_id, status, node_name FROM approval_task
                                   WHERE instance_id=:i ORDER BY id"""), {"i": iid}).fetchall()
        for t in tasks:
            if t.assignee_id == 2:
                create_t, update_t = create, (mgr or create)
            else:
                create_t = mgr or create
                update_t = leader or create_t
            db.execute(text("UPDATE approval_task SET create_time=:c, update_time=:u WHERE id=:id"),
                       {"c": create_t, "u": update_t, "id": t.id})
        # 审计
        db.execute(text("""UPDATE sys_audit_log SET create_time=:u
                           WHERE biz_type='purchase_request' AND biz_id=:id"""),
                   {"u": last, "id": r.id})
        db.execute(text("""UPDATE sys_notify SET create_time=:c, update_time=:c
                           WHERE biz_type='purchase_request' AND biz_id=:id AND create_time>='2026-10-27'"""),
                   {"c": create, "id": r.id})
    print("requests 时间线完成:", len(rows))

    # ---------------- 合同时间线 ----------------
    CON_TL = {
        # name: (create, t1a(manager会签), t1b(leader会签), t2(终审) or None)
        "CG": None,  # 占位，按 request 关联处理
    }
    con_rows = db.execute(text("""SELECT id, name, request_id, status, flow_instance_id, request_no
                                  FROM pur_contract WHERE deleted=0""")).fetchall()
    # 由申请时间推导：生成合同 = 申请通过后当天
    req_last = {r.title: (leader or mgr or create) for r in rows
                for create, mgr, leader in [REQ_TL[r.title]]}
    gen_con_tl = {
        "风洞应变片与力学传感器年度采购": ("2026-09-23 16:10", "2026-09-24 09:50", "2026-09-24 15:10", "2026-09-25 10:35"),
        "实验室标准气体与标准物质采购": ("2026-09-28 10:20", "2026-09-29 09:40", "2026-09-29 14:30", "2026-09-30 10:50"),
        "数据采集系统板卡扩容": ("2026-10-13 14:40", "2026-10-14 09:35", "2026-10-14 15:25", "2026-10-15 11:15"),
        "试验数据服务器与存储备件采购": ("2026-10-16 10:05", "2026-10-19 09:45", "2026-10-19 14:50", "2026-10-20 10:45"),
    }
    direct_con_tl = {
        "计量校准服务年度协议（武汉科仪）": ("2026-10-20 15:50", "2026-10-21 09:30", None, None),
        "实验室玻璃器皿批量采购合同（博远）": ("2026-10-23 11:40", None, None, None),
    }
    for c in con_rows:
        if c.request_id:
            title = db.execute(text("SELECT title FROM pur_request WHERE id=:i"), {"i": c.request_id}).scalar()
            create, t1a, t1b, t2 = gen_con_tl[title]
        else:
            create, t1a, t1b, t2 = direct_con_tl[c.name]
        last = t2 or t1b or t1a or create
        db.execute(text("""UPDATE pur_contract SET create_time=:c, update_time=:u, create_by=1 WHERE id=:id"""),
                   {"c": create, "u": last, "id": c.id})
        if c.status == "approved":
            db.execute(text("UPDATE pur_contract SET sign_date=:d WHERE id=:id AND sign_date IS NULL"),
                       {"d": last[:10], "id": c.id})
        if not c.flow_instance_id:
            continue
        iid = c.flow_instance_id
        db.execute(text("UPDATE approval_instance SET create_time=:c, update_time=:u WHERE id=:iid"),
                   {"c": create, "u": last, "iid": iid})
        rec_times = [create] + [t for t in (t1a, t1b, t2) if t]
        recs = db.execute(text("SELECT id FROM approval_record WHERE instance_id=:i ORDER BY id"),
                          {"i": iid}).fetchall()
        for idx, rec in enumerate(recs):
            t = rec_times[idx] if idx < len(rec_times) else last
            db.execute(text("UPDATE approval_record SET create_time=:t, update_time=:t WHERE id=:id"),
                       {"t": t, "id": rec.id})
        tasks = db.execute(text("""SELECT id, assignee_id, status, node_name FROM approval_task
                                   WHERE instance_id=:i ORDER BY id"""), {"i": iid}).fetchall()
        for t in tasks:
            if t.node_name and "终审" in t.node_name:
                create_t = t1b or t1a or create
                update_t = t2 or create_t
            else:  # 会签节点（and，两任务：manager1=2 → t1a；leader1=3 → t1b）
                create_t = create
                if t.status in ("pending", "todo", None):
                    update_t = create_t
                else:
                    update_t = t1a if t.assignee_id == 2 else (t1b or t1a or create)
            db.execute(text("UPDATE approval_task SET create_time=:c, update_time=:u WHERE id=:id"),
                       {"c": create_t, "u": update_t, "id": t.id})
        db.execute(text("""UPDATE sys_audit_log SET create_time=:u WHERE biz_type='purchase_contract' AND biz_id=:id"""),
                   {"u": last, "id": c.id})
        db.execute(text("""UPDATE sys_notify SET create_time=:c, update_time=:c
                           WHERE biz_type='purchase_contract' AND biz_id=:id AND create_time>='2026-10-27'"""),
                   {"c": create, "id": c.id})
    print("contracts 时间线完成:", len(con_rows))

    # ---------------- 出入库时间线 ----------------
    STOCK_TL = {
        # order_no 当前(重排前按创建序): 用 (register, confirm|None)
        "in": [
            ("2026-09-29 10:30", "2026-09-30 15:20"),
            ("2026-10-09 10:15", "2026-10-12 09:55"),
            ("2026-10-20 09:50", "2026-10-21 14:10"),
            ("2026-10-23 10:40", "2026-10-26 09:35"),
            ("2026-10-26 14:25", None),
        ],
        "out": [
            ("2026-10-12 11:05", "2026-10-13 10:05"),
            ("2026-10-15 15:35", "2026-10-16 10:20"),
            ("2026-10-26 11:15", None),
            ("2026-10-26 16:10", None),
        ],
    }
    for typ, tls in STOCK_TL.items():
        orders = db.execute(text("""SELECT id FROM pur_stock_order WHERE order_type=:t AND deleted=0 ORDER BY id"""),
                            {"t": typ}).fetchall()
        assert len(orders) == len(tls), f"{typ} 数量不符 {len(orders)} vs {len(tls)}"
        for o, (reg, conf) in zip(orders, tls):
            upd = conf or reg
            db.execute(text("""UPDATE pur_stock_order SET create_time=:c, update_time=:u, order_date=:d, create_by=1
                               WHERE id=:id"""), {"c": reg, "u": upd, "d": reg[:10], "id": o.id})
            db.execute(text("UPDATE pur_stock_item SET create_time=:c, update_time=:c WHERE order_id=:id"),
                       {"c": reg, "id": o.id})
            db.execute(text("""UPDATE sys_audit_log SET create_time=:u WHERE biz_type IN ('stock_order','purchase_stock')
                               AND biz_id=:id"""), {"u": upd, "id": o.id})
            db.execute(text("""UPDATE sys_notify SET create_time=:c, update_time=:c
                               WHERE biz_id=:id AND create_time>='2026-10-27'"""), {"c": reg, "id": o.id})
    print("stock 时间线完成")

    # ---------------- 重排单号 ----------------
    def renumber(table, no_col, prefix, date_col="create_time"):
        rows2 = db.execute(text(f"SELECT id, {date_col} AS d FROM {table} WHERE deleted=0 AND {no_col}<>'' ORDER BY {date_col}, id")).fetchall()
        seq: dict[str, int] = {}
        mapping = {}
        for r in rows2:
            key = r.d.strftime("%Y%m%d")
            seq[key] = seq.get(key, 0) + 1
            new = f"{prefix}{key}{seq[key]:04d}"
            old = db.execute(text(f"SELECT {no_col} FROM {table} WHERE id=:i"), {"i": r.id}).scalar()
            if old != new:
                mapping[old] = new
                db.execute(text(f"UPDATE {table} SET {no_col}=:n WHERE id=:i"), {"n": new, "i": r.id})
        return mapping

    m_req = renumber("pur_request", "request_no", "PR")
    m_con = renumber("pur_contract", "contract_no", "CG")
    # 出入库按类型分别编号（RK 入 / CK 出）
    for typ, prefix in (("in", "RK"), ("out", "CK")):
        rows3 = db.execute(text("""SELECT id, create_time AS d FROM pur_stock_order
                                   WHERE deleted=0 AND order_type=:t ORDER BY create_time, id"""), {"t": typ}).fetchall()
        seq = {}
        for r in rows3:
            key = r.d.strftime("%Y%m%d")
            seq[key] = seq.get(key, 0) + 1
            db.execute(text("UPDATE pur_stock_order SET order_no=:n WHERE id=:i"),
                       {"n": f"{prefix}{key}{seq[key]:04d}", "i": r.id})
    # 冗余同步 + 审批标题/快照
    for old, new in list(m_req.items()):
        db.execute(text("UPDATE pur_contract SET request_no=:n WHERE request_no=:o"), {"n": new, "o": old})
    # 合同号冗余：stock.contract_no
    con_no_map = {}
    for r in db.execute(text("SELECT id, contract_no FROM pur_contract WHERE deleted=0")).fetchall():
        con_no_map[r.id] = r.contract_no
    # 用新号覆盖（pur_contract.contract_no 已更新，stock 冗余同步）
    for cid, cno in con_no_map.items():
        db.execute(text("UPDATE pur_stock_order SET contract_no=:n WHERE contract_id=:i"), {"n": cno, "i": cid})

    # 审批实例标题与快照中的旧号
    for old, new in {**m_req, **m_con}.items():
        db.execute(text("""UPDATE approval_instance SET title=REPLACE(title, :o, :n) WHERE title LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE approval_instance SET form_snapshot=REPLACE(form_snapshot, :o, :n)
                           WHERE form_snapshot IS NOT NULL AND form_snapshot LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE approval_instance SET variables=REPLACE(variables, :o, :n)
                           WHERE variables IS NOT NULL AND variables LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE approval_record SET comment=REPLACE(comment, :o, :n)
                           WHERE comment IS NOT NULL AND comment LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
    db.commit()
    print("重排: 申请", len(m_req), "合同", len(m_con))

    # ---------------- 校验 ----------------
    bad_hours = db.execute(text("""SELECT COUNT(*) FROM (
        SELECT create_time FROM pur_request WHERE deleted=0
        UNION ALL SELECT create_time FROM pur_contract WHERE deleted=0
        UNION ALL SELECT create_time FROM pur_stock_order WHERE deleted=0) t
        WHERE HOUR(create_time)<8 OR HOUR(create_time)>=20""")).scalar()
    bad_order = db.execute(text("""SELECT COUNT(*) FROM pur_request r JOIN approval_instance i ON i.id=r.flow_instance_id
                                   WHERE r.create_time > i.create_time""")).scalar()
    nums = db.execute(text("""SELECT request_no FROM pur_request WHERE deleted=0 AND request_no<>'' ORDER BY request_no""")).fetchall()
    cnums = db.execute(text("""SELECT contract_no FROM pur_contract WHERE deleted=0 AND contract_no<>'' ORDER BY contract_no""")).fetchall()
    onums = db.execute(text("""SELECT order_no FROM pur_stock_order WHERE deleted=0 ORDER BY order_no""")).fetchall()
    print("工时越界(应0):", bad_hours, "| 申请晚于实例(应0):", bad_order)
    print("PR:", [x[0] for x in nums])
    print("CG:", [x[0] for x in cnums])
    print("单号:", [x[0] for x in onums])
    # 残留旧号检查
    leftover = db.execute(text("""SELECT COUNT(*) FROM approval_instance
                                  WHERE (title LIKE '%20261027%' OR IFNULL(form_snapshot,'') LIKE '%20261027%'
                                         OR IFNULL(variables,'') LIKE '%20261027%')
                                  AND biz_type LIKE 'purchase%'""")).scalar()
    print("审批中残留20261027(应0):", leftover)
finally:
    db.close()
print("PROCUREMENT_BACKDATE_DONE")
