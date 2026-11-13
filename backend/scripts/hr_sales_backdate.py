"""工时/报价演示数据回填：时间线 + BJ 重排 + 关联同步。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.core.db import SessionLocal

db = SessionLocal()
try:
    # ---------- 1. 工时：create/update = 工作日当天（错峰工作时段） ----------
    TS_TL = {1: "2026-11-09 09:35", 2: "2026-11-10 10:40", 3: "2026-11-11 15:10",
             4: "2026-11-10 14:20", 5: "2026-11-11 16:05", 6: "2026-11-12 09:50",
             7: "2026-11-12 14:30", 8: "2026-11-13 10:15", 9: "2026-11-11 09:45"}
    for tid, t in TS_TL.items():
        db.execute(text("""UPDATE hr_timesheet SET create_time=:t, update_time=:t, create_by=user_id
                           WHERE id=:id"""), {"t": t, "id": tid})
        db.execute(text("""UPDATE sys_audit_log SET create_time=:t
                           WHERE action='hr_timesheet_create' AND biz_id=:id"""), {"t": t, "id": tid})
    print("工时时间线完成:", len(TS_TL))

    # ---------- 2. 报价 Q1（草稿） ----------
    db.execute(text("""UPDATE sales_quotation SET create_time='2026-11-10 09:40',
                       update_time='2026-11-10 09:40', create_by=1 WHERE id=1"""))
    db.execute(text("UPDATE sales_quotation_item SET create_time='2026-11-10 09:40', update_time='2026-11-10 09:40' WHERE quotation_id=1"))

    # ---------- 3. 报价 Q2 全链 ----------
    db.execute(text("""UPDATE sales_quotation SET create_time='2026-11-10 14:20', update_time='2026-11-12 15:30',
                       create_by=1 WHERE id=2"""))
    db.execute(text("UPDATE sales_quotation_item SET create_time='2026-11-10 14:20', update_time='2026-11-10 14:20' WHERE quotation_id=2"))
    db.execute(text("""UPDATE approval_instance SET create_time='2026-11-10 16:10', update_time='2026-11-11 15:40'
                       WHERE id=215"""))
    # 记录：start / agree / agree
    rec_t = ["2026-11-10 16:10", "2026-11-11 10:30", "2026-11-11 15:40"]
    recs = db.execute(text("SELECT id FROM approval_record WHERE instance_id=215 ORDER BY id")).fetchall()
    for i, r in enumerate(recs):
        t = rec_t[i] if i < len(rec_t) else "2026-11-11 15:40"
        db.execute(text("UPDATE approval_record SET create_time=:t, update_time=:t WHERE id=:id"), {"t": t, "id": r.id})
    # 任务：319(manager,节点1) create=submit update=node1；320(leader,节点2) create=node1 update=node2
    db.execute(text("""UPDATE approval_task SET create_time='2026-11-10 16:10', update_time='2026-11-11 10:30'
                       WHERE id=319"""))
    db.execute(text("""UPDATE approval_task SET create_time='2026-11-11 10:30', update_time='2026-11-11 15:40'
                       WHERE id=320"""))
    db.execute(text("""UPDATE sales_quote_send_log SET create_time='2026-11-12 10:15', update_time='2026-11-12 10:15'
                       WHERE quotation_id=2"""))
    db.execute(text("""UPDATE sales_quotation SET update_time='2026-11-12 10:15' WHERE id=2"""))  # 临时，随后被终态覆盖
    db.execute(text("""UPDATE sales_quotation SET update_time='2026-11-12 15:30' WHERE id=2"""))
    # 转出的合同
    db.execute(text("""UPDATE ctr_contract SET create_time='2026-11-12 15:30', update_time='2026-11-12 15:30',
                       create_by=1 WHERE id=104"""))
    print("Q2 时间线完成")

    # ---------- 4. 报价 Q3（审批中） ----------
    db.execute(text("""UPDATE sales_quotation SET create_time='2026-11-11 09:50', update_time='2026-11-11 11:00',
                       create_by=1 WHERE id=3"""))
    db.execute(text("UPDATE sales_quotation_item SET create_time='2026-11-11 09:50', update_time='2026-11-11 09:50' WHERE quotation_id=3"))
    db.execute(text("""UPDATE approval_instance SET create_time='2026-11-11 11:00', update_time='2026-11-11 11:00'
                       WHERE id=216"""))
    db.execute(text("""UPDATE approval_record SET create_time='2026-11-11 11:00', update_time='2026-11-11 11:00'
                       WHERE instance_id=216"""))
    db.execute(text("""UPDATE approval_task SET create_time='2026-11-11 11:00', update_time='2026-11-11 11:00'
                       WHERE id=321"""))
    print("Q3 时间线完成")

    # ---------- 5. 预置模板回填 ----------
    db.execute(text("""UPDATE sales_quote_template SET create_time='2026-10-30 10:00', update_time='2026-10-30 10:00'
                       WHERE create_time >= '2026-11-13'"""))

    # ---------- 6. 审计 / 通知 映射 ----------
    AUDIT = {}
    for tid, t in TS_TL.items():
        AUDIT[("hr_timesheet_create", tid)] = t
    AUDIT.update({
        ("sales_quote_create", 1): "2026-11-10 09:40",
        ("sales_quote_create", 2): "2026-11-10 14:20",
        ("sales_quote_create", 3): "2026-11-11 09:50",
        ("sales_quote_submit", 2): "2026-11-10 16:10",
        ("sales_quote_submit", 3): "2026-11-11 11:00",
        ("sales_quote_send", 2): "2026-11-12 10:15",
        ("sales_quote_feedback", 2): "2026-11-12 15:20",
        ("sales_quote_to_contract", 2): "2026-11-12 15:30",
    })
    rows = db.execute(text("""SELECT id, action, biz_id, module FROM sys_audit_log
                              WHERE create_time >= '2026-11-13'
                                AND module IN ('hr','sales','approval')""")).fetchall()
    fixed = 0
    unmapped = []
    # 审批模块的报价审批动作：按实例分组映射
    appr = [r for r in rows if r.module == "approval"]
    appr.sort(key=lambda r: r.id)
    appr_t = {215: ["2026-11-11 10:30", "2026-11-11 15:40"], 216: []}
    appr_idx: dict[int, int] = {}
    for r in appr:
        # detail 里可能有 instanceId；兜底按 biz_id=报价id
        qid = r.biz_id
        inst = {2: 215, 3: 216}.get(qid)
        k = appr_idx.get(inst, 0)
        t = appr_t.get(inst, [])[k] if inst and k < len(appr_t.get(inst, [])) else None
        appr_idx[inst] = k + 1
        if t:
            db.execute(text("UPDATE sys_audit_log SET create_time=:t WHERE id=:id"), {"t": t, "id": r.id})
            fixed += 1
        else:
            unmapped.append((r.id, r.action, qid))
    for r in rows:
        if r.module == "approval":
            continue
        t = AUDIT.get((r.action, r.biz_id))
        if t:
            db.execute(text("UPDATE sys_audit_log SET create_time=:t WHERE id=:id"), {"t": t, "id": r.id})
            fixed += 1
        else:
            unmapped.append((r.id, r.action, r.biz_id))
    # 通知：654/655 → Q2 提交/进节点2；656 → Q3 提交
    NOTIFY = {654: "2026-11-10 16:10", 655: "2026-11-11 10:30", 656: "2026-11-11 11:00"}
    for nid, t in NOTIFY.items():
        db.execute(text("UPDATE sys_notify SET create_time=:t, update_time=:t WHERE id=:id"), {"t": t, "id": nid})
    print(f"审计映射 {fixed} 行；未映射: {unmapped}")

    # ---------- 7. BJ 重排 ----------
    rows2 = db.execute(text("""SELECT id, create_time AS d FROM sales_quotation
                               WHERE deleted=0 AND quote_no IS NOT NULL AND quote_no<>''
                               ORDER BY create_time, id""")).fetchall()
    seq: dict[str, int] = {}
    mapping = {}
    for r in rows2:
        key = r.d.strftime("%Y%m%d")
        seq[key] = seq.get(key, 0) + 1
        new = f"BJ{key}{seq[key]:04d}"
        old = db.execute(text("SELECT quote_no FROM sales_quotation WHERE id=:i"), {"i": r.id}).scalar()
        if old != new:
            mapping[old] = new
            db.execute(text("UPDATE sales_quotation SET quote_no=:n WHERE id=:i"), {"n": new, "i": r.id})
    for old, new in mapping.items():
        db.execute(text("""UPDATE approval_instance SET title=REPLACE(title,:o,:n) WHERE title LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE approval_instance SET form_snapshot=REPLACE(form_snapshot,:o,:n)
                           WHERE form_snapshot IS NOT NULL AND form_snapshot LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE sys_notify SET title=REPLACE(title,:o,:n) WHERE title LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
        db.execute(text("""UPDATE sys_audit_log SET detail=REPLACE(detail,:o,:n)
                           WHERE detail IS NOT NULL AND detail LIKE CONCAT('%',:o2,'%')"""),
                   {"o": old, "n": new, "o2": old})
    db.commit()
    print("BJ 重排:", mapping)

    # ---------- 8. 校验 ----------
    bad_hours = db.execute(text("""SELECT COUNT(*) FROM (
        SELECT create_time FROM sales_quotation WHERE deleted=0
        UNION ALL SELECT create_time FROM hr_timesheet WHERE deleted=0) t
        WHERE HOUR(create_time)<8 OR HOUR(create_time)>=20""")).scalar()
    leftover = db.execute(text("""SELECT COUNT(*) FROM sys_audit_log
                                  WHERE create_time>='2026-11-13'
                                  AND (module IN ('hr','sales')
                                       OR (module='approval' AND biz_type='sales_quotation'))""")).scalar()
    print("工时越界(应0):", bad_hours, "| 今日遗留审计(应0):", leftover)
    for row in db.execute(text("""SELECT quote_no, status, create_time FROM sales_quotation
                                  WHERE deleted=0 ORDER BY id""")).fetchall():
        print(" ", row.quote_no, row.status, row.create_time)
finally:
    db.close()
print("HR_SALES_BACKDATE_DONE")
