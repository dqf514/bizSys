"""采购二期演示数据回填：招投标/门户/联系人附件/样品出入库时间线 + ZB/CG/RK/CK 重排 + 关联同步。"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import text

from app.core.db import SessionLocal

D = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")  # noqa: E731

db = SessionLocal()
try:
    # ---------- 1. 合作方账号 ----------
    partner_tl = {
        "szhuace": ("2026-10-14 09:30", "2026-10-15 10:20", "2026-10-21 09:35"),
        "szmaichuang": ("2026-10-15 10:40", "2026-10-16 11:10", "2026-10-21 10:05"),
        "gzlianyi": ("2026-10-16 14:20", None, None),
    }
    for u, (c, rev, login) in partner_tl.items():
        db.execute(text("""UPDATE partner_user SET create_time=:c, update_time=:u2, create_by=1
                           WHERE username=:u"""),
                   {"c": c, "u2": rev or c, "u": u})
        if login:
            db.execute(text("UPDATE partner_user SET last_login_at=:t WHERE username=:u"),
                       {"t": login, "u": u})
            db.execute(text("UPDATE sys_login_log SET create_time=:t, update_time=:t WHERE username=:n"),
                       {"t": login, "n": f"portal:{u}"})
    print("partners 时间线完成")

    # ---------- 2. 招标项目 ----------
    TENDER_TL = {
        # id: (create, update, reg_dl, bid_dl, open_t)
        1: ("2026-10-13 10:15", "2026-10-25 11:20", "2026-10-18 17:00", "2026-10-23 17:00", "2026-10-24 09:30"),
        2: ("2026-10-23 09:50", "2026-10-25 10:30", None, None, None),   # 截止保持未来
        3: ("2026-10-26 15:10", "2026-10-26 15:10", None, None, None),
        4: ("2026-10-17 10:40", "2026-10-19 16:05", "2026-10-25 17:00", "2026-10-30 17:00", "2026-10-31 09:30"),
    }
    for tid, (c, u, reg, bid, op) in TENDER_TL.items():
        sets, params = ["create_time=:c", "update_time=:u2", "create_by=1"], {"c": c, "u2": u, "tid": tid}
        if reg:
            sets += ["reg_deadline=:reg", "bid_deadline=:bid", "open_time=:op"]
            params |= {"reg": reg, "bid": bid, "op": op}
        db.execute(text(f"UPDATE pur_tender SET {', '.join(sets)} WHERE id=:tid"), params)
    print("tenders 时间线完成")

    # ---------- 3. 报名 / 投标 / 评标 ----------
    REG_TL = {1: ("2026-10-15 10:30", "2026-10-16 10:45"),
              2: ("2026-10-16 15:20", "2026-10-17 11:30"),
              3: ("2026-10-25 10:30", None)}
    for rid, (c, rev) in REG_TL.items():
        db.execute(text("""UPDATE pur_tender_registration SET create_time=:c, update_time=:u2, create_by=1,
                           review_at=:rev WHERE id=:rid"""),
                   {"c": c, "u2": rev or c, "rev": rev, "rid": rid})
    BID_TL = {1: "2026-10-21 14:20", 2: "2026-10-22 16:10"}
    for bid, t in BID_TL.items():
        db.execute(text("""UPDATE pur_tender_bid SET create_time=:t, update_time=:t, create_by=1, submit_at=:t2
                           WHERE id=:id"""),
                   {"t": t, "t2": t, "id": bid})
    EVAL_TL = ["2026-10-24 10:30", "2026-10-24 11:15", "2026-10-24 14:40", "2026-10-24 16:20"]
    evals = db.execute(text("SELECT id FROM pur_tender_eval WHERE deleted=0 ORDER BY id")).fetchall()
    for e, t in zip(evals, EVAL_TL):
        db.execute(text("UPDATE pur_tender_eval SET create_time=:t, update_time=:t, create_by=1 WHERE id=:id"),
                   {"t": t, "id": e.id})
    print(f"registrations={len(REG_TL)} bids={len(BID_TL)} evals={len(evals)} 时间线完成")

    # ---------- 4. 定标审批（ZB1） ----------
    t1 = db.execute(text("SELECT flow_instance_id FROM pur_tender WHERE id=1")).scalar()
    if t1:
        db.execute(text("""UPDATE approval_instance SET create_time='2026-10-24 16:45',
                           update_time='2026-10-25 10:15' WHERE id=:i"""), {"i": t1})
        recs = db.execute(text("SELECT id FROM approval_record WHERE instance_id=:i ORDER BY id"), {"i": t1}).fetchall()
        for idx, r in enumerate(recs):
            t = "2026-10-24 16:45" if idx == 0 else "2026-10-25 10:15"
            db.execute(text("UPDATE approval_record SET create_time=:t, update_time=:t WHERE id=:id"),
                       {"t": t, "id": r.id})
        tasks = db.execute(text("SELECT id FROM approval_task WHERE instance_id=:i"), {"i": t1}).fetchall()
        for tk in tasks:
            db.execute(text("""UPDATE approval_task SET create_time='2026-10-24 16:45',
                               update_time='2026-10-25 10:15' WHERE id=:id"""), {"id": tk.id})
        print("定标审批时间线完成")

    # ---------- 5. 中标合同 CG（contract id=7） ----------
    c7 = db.execute(text("SELECT flow_instance_id FROM pur_contract WHERE id=7")).scalar()
    db.execute(text("""UPDATE pur_contract SET create_time='2026-10-25 11:20', update_time='2026-10-26 16:40',
                       create_by=1, sign_date='2026-10-26' WHERE id=7"""))
    if c7:
        db.execute(text("""UPDATE approval_instance SET create_time='2026-10-25 16:30',
                           update_time='2026-10-26 16:40' WHERE id=:i"""), {"i": c7})
        ctimes = ["2026-10-25 16:30", "2026-10-26 10:20", "2026-10-26 15:10", "2026-10-26 16:40"]
        recs = db.execute(text("SELECT id FROM approval_record WHERE instance_id=:i ORDER BY id"), {"i": c7}).fetchall()
        for idx, r in enumerate(recs):
            t = ctimes[idx] if idx < len(ctimes) else "2026-10-26 16:40"
            db.execute(text("UPDATE approval_record SET create_time=:t, update_time=:t WHERE id=:id"),
                       {"t": t, "id": r.id})
        tasks = db.execute(text("""SELECT id, node_name FROM approval_task WHERE instance_id=:i ORDER BY id"""),
                           {"i": c7}).fetchall()
        for tk in tasks:
            if tk.node_name and "终审" in tk.node_name:
                c, u = "2026-10-26 15:10", "2026-10-26 16:40"
            else:
                c, u = "2026-10-25 16:30", None
            if u is None:
                u = "2026-10-26 10:20" if "10:20" else c
                # 会签两任务：manager=10-26 10:20；leader=10-26 15:10 —— 按顺序推
            db.execute(text("UPDATE approval_task SET create_time=:c, update_time=:u WHERE id=:id"),
                       {"c": c, "u": u, "id": tk.id})
        # 精确覆盖会签两任务时间
        tasks2 = db.execute(text("""SELECT id, assignee_id FROM approval_task WHERE instance_id=:i
                                    ORDER BY id"""), {"i": c7}).fetchall()
        for tk in tasks2:
            if tk.assignee_id == 2:
                db.execute(text("UPDATE approval_task SET update_time='2026-10-26 10:20' WHERE id=:id"),
                           {"id": tk.id})
            elif tk.assignee_id == 3:
                # 终审任务（node2）已在上面设置；会签 leader 任务 update=10-26 15:10
                db.execute(text("""UPDATE approval_task SET update_time='2026-10-26 15:10'
                                   WHERE id=:id AND node_name LIKE '%会签%'"""), {"id": tk.id})
    print("中标合同时间线完成")

    # ---------- 6. 样品出入库（source_type=sample；订单 id=10/11，样品 source_id=172/217） ----------
    for oid, (c, u) in {10: ("2026-10-22 10:30", "2026-10-22 15:20"),
                        11: ("2026-10-23 14:10", "2026-10-24 10:50")}.items():
        db.execute(text("""UPDATE pur_stock_order SET create_time=:c, update_time=:u, order_date=:d, create_by=1
                           WHERE id=:oid"""), {"c": c, "u": u, "d": c[:10], "oid": oid})
        db.execute(text("UPDATE pur_stock_item SET create_time=:c, update_time=:c WHERE order_id=:oid"),
                   {"c": c, "oid": oid})
        # 样品流水与样品状态回写时间
        sid = db.execute(text("SELECT source_id FROM pur_stock_order WHERE id=:oid"), {"oid": oid}).scalar()
        if sid:
            db.execute(text("UPDATE task_sample_flow SET create_time=:t, update_time=:t WHERE sample_id=:s"),
                       {"t": u, "s": sid})
            db.execute(text("UPDATE task_sample SET update_time=:t WHERE id=:s"), {"t": u, "s": sid})
    print("样品出入库时间线完成")

    # ---------- 7. 联系人 / 附件 ----------
    CONTACT_TL = {52: "2026-10-14 09:40", 54: "2026-10-15 10:50", 59: "2026-10-16 14:30"}
    for cid, t in CONTACT_TL.items():
        db.execute(text("""UPDATE crm_partner_contact SET create_time=:t, update_time=:t, create_by=1
                           WHERE customer_id=:cid"""), {"t": t, "cid": cid})
    ATT_TL = {52: "2026-10-14 10:10", 54: "2026-10-15 11:00"}
    for cid, t in ATT_TL.items():
        db.execute(text("""UPDATE crm_partner_attachment SET create_time=:t, update_time=:t, create_by=1
                           WHERE customer_id=:cid"""), {"t": t, "cid": cid})
    print("联系人/附件时间线完成")

    # ---------- 8. 审计 / 通知 / 登录日志（今天产生的一律映射） ----------
    AUDIT = {}  # (action, biz_id) -> time
    AUDIT.update({("tender_create", 1): "2026-10-13 10:15", ("tender_publish", 1): "2026-10-13 15:40",
                  ("tender_start_evaluation", 1): "2026-10-24 10:00", ("tender_award_submit", 1): "2026-10-24 16:45",
                  ("tender_generate_contract", 1): "2026-10-25 11:20",
                  ("tender_create", 2): "2026-10-23 09:50", ("tender_publish", 2): "2026-10-23 15:10",
                  ("tender_create", 3): "2026-10-26 15:10",
                  ("tender_create", 4): "2026-10-17 10:40", ("tender_publish", 4): "2026-10-17 14:15",
                  ("tender_terminate", 4): "2026-10-19 16:05",
                  ("partner_contact_create", 52): "2026-10-14 09:40",
                  ("partner_contact_create", 54): "2026-10-15 10:50",
                  ("partner_contact_create", 59): "2026-10-16 14:30",
                  ("partner_attachment_upload", 52): "2026-10-14 10:10",
                  ("partner_attachment_upload", 54): "2026-10-15 11:00",
                  ("purchase_contract_create", 6): "2026-10-23 11:40",   # C5 草稿（无审批实例）
                  ("purchase_contract_create", 7): "2026-10-25 11:20",
                  ("purchase_contract_submit", 7): "2026-10-25 16:30",
                  ("purchase_request_create", 8): "2026-10-22 11:10",
                  ("purchase_request_create", 9): "2026-10-23 16:05",
                  ("stock_order_create", 10): "2026-10-22 10:30",
                  ("stock_order_confirm", 10): "2026-10-22 15:20",
                  ("stock_order_create", 11): "2026-10-23 14:10",
                  ("stock_order_confirm", 11): "2026-10-24 10:50",
                  })
    EVAL_TIME_BY_SCORE = {"92": "2026-10-24 10:30", "89": "2026-10-24 11:15",
                          "84": "2026-10-24 14:40", "81": "2026-10-24 16:20"}
    reg_tl_flat = {1: ("2026-10-15 10:30", "2026-10-16 10:45"), 2: ("2026-10-16 15:20", "2026-10-17 11:30"),
                   3: ("2026-10-25 10:30", None)}
    bid_tl_flat = {1: "2026-10-21 14:20", 2: "2026-10-22 16:10"}
    part_tl = {"szhuace": ("2026-10-14 09:30", "2026-10-15 10:20"), "szmaichuang": ("2026-10-15 10:40", "2026-10-16 11:10"),
               "gzlianyi": ("2026-10-16 14:20", None)}
    uid_by_id = {1: "szhuace", 2: "szmaichuang", 3: "gzlianyi"}
    rows = db.execute(text("""SELECT id, action, biz_id, biz_type, detail FROM sys_audit_log
                              WHERE create_time >= '2026-10-27'
                                AND (module IN ('portal','procurement') OR action LIKE 'tender%'
                                     OR action LIKE 'partner%' OR action LIKE 'stock_order%'
                                     OR action LIKE 'purchase_contract%' OR action LIKE 'purchase_request%'
                                     OR action LIKE 'portal%')""")).fetchall()
    fixed = 0
    unmapped = []
    for r in rows:
        a, biz = r.action, r.biz_id
        t = AUDIT.get((a, biz))
        if t is None and a == "tender_register" and biz in reg_tl_flat:
            t = reg_tl_flat[biz][0]
        elif t is None and a == "tender_registration_approve" and biz in reg_tl_flat:
            t = reg_tl_flat[biz][1] or reg_tl_flat[biz][0]
        elif t is None and a == "tender_bid" and biz in bid_tl_flat:
            t = bid_tl_flat[biz]
        elif t is None and a == "tender_eval":
            sc = None
            try:
                sc = str(int(float(json.loads(r.detail or "{}").get("score", -1))))
            except Exception:
                pass
            t = EVAL_TIME_BY_SCORE.get(sc or "")
        elif t is None and a in ("partner_register", "partner_approve") and biz in uid_by_id:
            u = uid_by_id[biz]
            t = part_tl[u][1] or part_tl[u][0]
        elif t is None and a.startswith("portal_login"):
            u = next((x for x in part_tl if r.detail and f'"{x}"' in r.detail), None)
            t = part_tl[u][1] if u and part_tl[u][1] else (part_tl[u][0] if u else None)
        if t:
            db.execute(text("UPDATE sys_audit_log SET create_time=:t WHERE id=:id"), {"t": t, "id": r.id})
            fixed += 1
        else:
            unmapped.append((r.id, a, biz))
    # 通知：650 定标待办；651/652 合同会签待办（提交时建）；653 终审待办（进入终审建）
    NOTIFY_TL = {650: "2026-10-24 16:45", 651: "2026-10-25 16:30", 652: "2026-10-25 16:30",
                 653: "2026-10-26 15:10"}
    for nid, t in NOTIFY_TL.items():
        db.execute(text("UPDATE sys_notify SET create_time=:t, update_time=:t WHERE id=:id"),
                   {"t": t, "id": nid})
    print(f"审计映射 {fixed} 行；未映射(应仅 id11 用户test单): {unmapped}")
    print(f"通知映射 {len(NOTIFY_TL)} 行")

    # ---------- 9. 重排单号 ----------
    def renumber(table, no_col, prefix, extra_where=""):
        rows2 = db.execute(text(
            f"SELECT id, create_time AS d FROM {table} WHERE deleted=0 AND {no_col} IS NOT NULL AND {no_col}<>'' "
            f"{extra_where} ORDER BY create_time, id")).fetchall()
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

    m_tender = renumber("pur_tender", "tender_no", "ZB")
    m_req = renumber("pur_request", "request_no", "PR")
    m_con = renumber("pur_contract", "contract_no", "CG")
    for typ, prefix in (("in", "RK"), ("out", "CK")):
        rows3 = db.execute(text("""SELECT id, create_time AS d FROM pur_stock_order
                                   WHERE deleted=0 AND order_type=:t ORDER BY create_time, id"""), {"t": typ}).fetchall()
        seq = {}
        for r in rows3:
            key = r.d.strftime("%Y%m%d")
            seq[key] = seq.get(key, 0) + 1
            db.execute(text("UPDATE pur_stock_order SET order_no=:n WHERE id=:i"),
                       {"n": f"{prefix}{key}{seq[key]:04d}", "i": r.id})
    print(f"重排: ZB {len(m_tender)} PR {len(m_req)} CG {len(m_con)}")

    # 冗余 + 审批标题/快照同步
    for old, new in m_req.items():
        db.execute(text("UPDATE pur_contract SET request_no=:n WHERE request_no=:o"), {"n": new, "o": old})
    for r in db.execute(text("SELECT id, contract_no FROM pur_contract WHERE deleted=0")).fetchall():
        db.execute(text("UPDATE pur_stock_order SET contract_no=:n WHERE contract_id=:i"),
                   {"n": r.contract_no, "i": r.id})
    for old, new in {**m_tender, **m_con}.items():
        for col in ("title",):
            db.execute(text(f"UPDATE approval_instance SET {col}=REPLACE({col},:o,:n) WHERE {col} LIKE CONCAT('%',:o2,'%')"),
                       {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE approval_instance SET form_snapshot=REPLACE(form_snapshot,:o,:n)
                           WHERE form_snapshot IS NOT NULL AND form_snapshot LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE approval_instance SET variables=REPLACE(variables,:o,:n)
                           WHERE variables IS NOT NULL AND variables LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
    # 招标表里可能冗余存了 ZB 号（announcement/remark）
    for old, new in m_tender.items():
        db.execute(text("""UPDATE pur_tender_announcement_placeholder SET x=1 WHERE 1=0""")) if False else None
    db.commit()

    # ---------- 10. 校验 ----------
    bad_hours = db.execute(text("""SELECT COUNT(*) FROM (
        SELECT create_time FROM pur_tender WHERE deleted=0
        UNION ALL SELECT create_time FROM pur_tender_registration WHERE deleted=0
        UNION ALL SELECT create_time FROM pur_tender_bid WHERE deleted=0
        UNION ALL SELECT create_time FROM pur_tender_eval WHERE deleted=0
        UNION ALL SELECT create_time FROM partner_user WHERE deleted=0
        UNION ALL SELECT create_time FROM crm_partner_contact WHERE deleted=0
        UNION ALL SELECT create_time FROM crm_partner_attachment WHERE deleted=0) t
        WHERE HOUR(create_time)<8 OR HOUR(create_time)>=20""")).scalar()
    leftover = db.execute(text("""SELECT COUNT(*) FROM sys_audit_log
                                  WHERE create_time>='2026-10-27' AND (module IN ('portal','procurement')
                                  OR action LIKE 'tender%' OR action LIKE 'partner%' OR action LIKE 'stock_order%'
                                  OR action LIKE 'portal%')
                                  AND NOT (action='purchase_request_create' AND biz_id=11)""")).scalar()
    zb = db.execute(text("SELECT tender_no, status, create_time FROM pur_tender WHERE deleted=0 ORDER BY create_time")).fetchall()
    cg = db.execute(text("SELECT contract_no, status, create_time FROM pur_contract WHERE deleted=0 AND contract_no<>'' ORDER BY create_time")).fetchall()
    print("工时越界(应0):", bad_hours, "| 今日遗留审计(应0):", leftover)
    print("ZB:", [(x[0], x[1]) for x in zb])
    print("CG:", [x[0] for x in cg])
    print("审批残留20261027(应0):", db.execute(text("""SELECT COUNT(*) FROM approval_instance
        WHERE biz_type IN ('tender_award','purchase_contract') AND (title LIKE '%20261027%'
        OR IFNULL(form_snapshot,'') LIKE '%20261027%')""")).scalar())
finally:
    db.close()
print("PHASE2_BACKDATE_DONE")
