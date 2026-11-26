"""安全巡检域（B8 / CSV 24）种子数据。

幂等导入：按业务编号（plan_no / record_no / hazard_no）判断是否已存在，重复执行不会产生重复行。
示例内容全部为通用业务词，**不含任何真实姓名 / 手机 / 邮箱 / 证件号** —— 人员一律写岗位名。

由 `app/seeds/init_data.py::main()` 调用。
"""

import json
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.safety.models import SafetyHazard, SafetyInspection, SafetyInspectionPlan

# 三类单号的编号规则（`safety_plan` / `safety_inspection` / `safety_hazard`，前缀 JH / XJ / YH）
# 由 `app/seeds/init_data.py::NUMBER_RULES` 统一登记，本模块不再重复写入。


def _plan(db: Session, plan_no: str) -> SafetyInspectionPlan | None:
    return db.scalar(select(SafetyInspectionPlan).where(SafetyInspectionPlan.plan_no == plan_no))


def _inspection(db: Session, record_no: str) -> SafetyInspection | None:
    return db.scalar(select(SafetyInspection).where(SafetyInspection.record_no == record_no))


def _hazard(db: Session, hazard_no: str) -> SafetyHazard | None:
    return db.scalar(select(SafetyHazard).where(SafetyHazard.hazard_no == hazard_no))


def import_safety(db: Session) -> dict[str, int]:
    """导入安全巡检演示数据（幂等）。

    返回本次**新建**的条数（已存在的跳过），与其他种子函数的返回口径一致。
    """
    today = date.today()
    now = datetime.now()
    created = {"plans": 0, "inspections": 0, "hazards": 0}

    # ---------------- 巡检计划 ----------------
    plan_specs = [
        {
            "plan_no": "JH202601150001",
            "name": "每日消防通道巡检",
            "plan_type": "daily",
            "target_area": "生产加工区",
            "check_items": ["消防通道畅通", "灭火器压力正常", "应急照明可用"],
            "cycle_days": 1,
            "next_date": today + timedelta(days=1),
            "owner_name": "安全主管",
            "dept_name": "安全环保部",
            "status": "active",
            "remark": "每日班后执行，结果当日提交",
        },
        {
            "plan_no": "JH202601160001",
            "name": "每周气瓶与危化品专项巡检",
            "plan_type": "weekly",
            "target_area": "工具仪器间",
            "check_items": ["气瓶固定牢靠", "通风设施运行正常", "危化品标签清晰"],
            "cycle_days": 7,
            "next_date": today + timedelta(days=5),
            "owner_name": "设备管理员",
            "dept_name": "设备管理部",
            "status": "active",
            "remark": "气瓶间属高风险区域，发现异常即刻上报",
        },
        {
            "plan_no": "JH202601170001",
            "name": "每月设备安全专项巡检",
            "plan_type": "monthly",
            "target_area": "数据机房",
            "check_items": ["配电柜密封完好", "备用电源状态正常", "机房门禁有效"],
            "cycle_days": 30,
            "next_date": today + timedelta(days=12),
            "owner_name": "设备管理员",
            "dept_name": "设备管理部",
            "status": "active",
            "remark": "月度专项，与设备台账联动复核",
        },
    ]
    plans: dict[str, SafetyInspectionPlan] = {}
    for spec in plan_specs:
        row = _plan(db, spec["plan_no"])
        if row is None:
            row = SafetyInspectionPlan(
                plan_no=spec["plan_no"],
                name=spec["name"],
                plan_type=spec["plan_type"],
                target_area=spec["target_area"],
                check_items=json.dumps(spec["check_items"], ensure_ascii=False),
                cycle_days=spec["cycle_days"],
                next_date=spec["next_date"],
                owner_name=spec["owner_name"],
                dept_name=spec["dept_name"],
                status=spec["status"],
                remark=spec["remark"],
            )
            db.add(row)
            db.flush()
            created["plans"] += 1
        plans[spec["plan_no"]] = row

    # ---------------- 巡检记录 ----------------
    inspection_specs = [
        {
            "record_no": "XJ202601150001",
            "plan_no": "JH202601150001",
            "area": "生产加工区",
            "inspect_date": today - timedelta(days=6),
            "inspector_name": "安全主管",
            "status": "closed",
            "summary": "各巡检项均正常，无异常",
            "items": [
                {"item": "消防通道畅通", "result": "normal", "note": ""},
                {"item": "灭火器压力正常", "result": "normal", "note": ""},
                {"item": "应急照明可用", "result": "normal", "note": ""},
            ],
        },
        {
            "record_no": "XJ202601160001",
            "plan_no": "JH202601160001",
            "area": "工具仪器间",
            "inspect_date": today - timedelta(days=4),
            "inspector_name": "设备管理员",
            "status": "submitted",
            "summary": "气瓶存放规范，通风正常",
            "items": [
                {"item": "气瓶固定牢靠", "result": "normal", "note": ""},
                {"item": "通风设施运行正常", "result": "normal", "note": ""},
                {"item": "危化品标签清晰", "result": "normal", "note": ""},
            ],
        },
        {
            "record_no": "XJ202601170001",
            "plan_no": "JH202601170001",
            "area": "数据机房",
            "inspect_date": today - timedelta(days=2),
            "inspector_name": "设备管理员",
            "status": "submitted",
            "summary": "发现配电柜密封条老化，已列为隐患跟踪整改",
            "items": [
                {"item": "配电柜密封完好", "result": "abnormal", "note": "配电柜密封条老化，存在进尘进水风险"},
                {"item": "备用电源状态正常", "result": "normal", "note": ""},
                {"item": "机房门禁有效", "result": "normal", "note": ""},
            ],
        },
        {
            "record_no": "XJ202601200001",
            "plan_no": "JH202601150001",
            "area": "生产加工区",
            "inspect_date": today - timedelta(days=1),
            "inspector_name": "实验室安全员",
            "status": "submitted",
            "summary": "消防通道有货物堆放，已现场清理并跟进隐患整改",
            "items": [
                {"item": "消防通道畅通", "result": "abnormal", "note": "消防通道北侧堆放周转箱，已现场清理"},
                {"item": "灭火器压力正常", "result": "normal", "note": ""},
                {"item": "应急照明可用", "result": "abnormal", "note": "应急照明灯具缺少一支备用灯管"},
            ],
        },
    ]
    inspections: dict[str, SafetyInspection] = {}
    for spec in inspection_specs:
        row = _inspection(db, spec["record_no"])
        if row is None:
            plan = plans.get(spec["plan_no"])
            abnormal = sum(1 for i in spec["items"] if i["result"] == "abnormal")
            row = SafetyInspection(
                record_no=spec["record_no"],
                plan_id=plan.id if plan else None,
                plan_name=plan.name if plan else "",
                area=spec["area"],
                inspect_date=spec["inspect_date"],
                inspector_name=spec["inspector_name"],
                result="abnormal" if abnormal else "normal",
                abnormal_count=abnormal,
                items_json=json.dumps(spec["items"], ensure_ascii=False),
                status=spec["status"],
                summary=spec["summary"],
            )
            db.add(row)
            db.flush()
            created["inspections"] += 1
        inspections[spec["record_no"]] = row

    # ---------------- 隐患 ----------------
    hazard_specs = [
        {
            "hazard_no": "YH202601170001",
            "record_no": "XJ202601170001",
            "description": "数据机房配电柜密封条老化，存在进尘进水风险",
            "level": "high",
            "status": "open",
            "responsible_name": "设备管理员",
            "deadline": today - timedelta(days=1),
            "found_at": now - timedelta(days=2),
            "remark": "配电柜密封条老化",
        },
        {
            "hazard_no": "YH202601180001",
            "record_no": "XJ202601200001",
            "description": "生产加工区消防通道北侧堆放周转箱，影响疏散通道畅通",
            "level": "medium",
            "status": "rectifying",
            "responsible_name": "安全主管",
            "deadline": today + timedelta(days=3),
            "found_at": now - timedelta(days=1),
            "measure": "已现场清理并划定线位标识，安排班组每日巡查",
            "rectified_at": now - timedelta(hours=6),
            "rectified_by_name": "安全主管",
            "remark": "消防通道畅通",
        },
        {
            "hazard_no": "YH202601190001",
            "record_no": "XJ202601200001",
            "description": "生产加工区应急照明灯具缺少一支备用灯管",
            "level": "low",
            "status": "closed",
            "responsible_name": "设备管理员",
            "deadline": today + timedelta(days=6),
            "found_at": now - timedelta(days=1),
            "measure": "已补装备用灯管并测试应急照明功能",
            "rectified_at": now - timedelta(days=1),
            "rectified_by_name": "设备管理员",
            "verify_result": "复测应急照明启动正常，符合现场要求",
            "verify_by_name": "安全主管",
            "verified_at": now - timedelta(hours=2),
            "remark": "应急照明可用",
        },
    ]
    for spec in hazard_specs:
        if _hazard(db, spec["hazard_no"]) is not None:
            continue
        insp = inspections.get(spec["record_no"])
        created["hazards"] += 1
        db.add(
            SafetyHazard(
                hazard_no=spec["hazard_no"],
                inspection_id=insp.id if insp else None,
                record_no=spec["record_no"],
                source="inspection",
                description=spec["description"],
                level=spec["level"],
                status=spec["status"],
                responsible_name=spec["responsible_name"],
                deadline=spec["deadline"],
                found_at=spec["found_at"],
                measure=spec.get("measure", ""),
                rectified_at=spec.get("rectified_at"),
                rectified_by_name=spec.get("rectified_by_name", ""),
                verify_result=spec.get("verify_result", ""),
                verify_by_name=spec.get("verify_by_name", ""),
                verified_at=spec.get("verified_at"),
                remark=spec.get("remark", ""),
            )
        )
    db.flush()
    return created
