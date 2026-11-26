"""B6 设备台账 / 能耗 / 预警 幂等种子（8 台设备 + 14 天能耗 + 2 条预警）。

设计约束：

- **幂等**：按 `equipment_no` 判重，已存在则整台跳过（含其能耗与预警），重复执行不产生重复数据。
- **不写任何真实个人信息**：责任人只写岗位角色名（设备主管 / 试验室主管 …），
  不含姓名、手机号、邮箱、证件号；`owner_id` 留空（不绑定真实账号）。
- **不新建组织 / 公司表**：部门 / 供应商列留空，由业务端通过 `sys_dept` / `crm_customer` 补齐。
- **能耗数据为推算样例**（`source` 多为 `schedule`），仅用于看板与预警规则演示；
  真实采集通道（Modbus / OPC-UA）本批次不落地 —— 见 `docs/roadmap-2026-11.md` B6 风险项。

用法（`app/seeds/init_data.py::main()` 中调用）::

    from app.seeds import equipment_seed
    equipment_seed.import_equipment(db)
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.asset.equipment_models import Equipment, EquipmentAlert, EquipmentMetric

# 随机种子固定 —— 保证多次执行得到同一组样例数据
_RNG_SEED = 20261126
_METRIC_DAYS = 14

# 设备台账样例：8 台（风洞 2 / CFD 计算集群 1 / 加工中心 3 / 试验台 2）
# 字段顺序：编号、名称、类别、型号、规格、车间、位置、原值、状态、保养周期、责任人角色
_EQUIPMENTS: list[dict] = [
    {
        "equipment_no": "EQ-WT-001",
        "name": "1 号低速风洞",
        "category": "wind_tunnel",
        "model": "WT-L1",
        "spec": "试验段 2.4m × 3.0m，最大风速 60 m/s",
        "workshop": "结构试验车间",
        "location": "试验楼 B1",
        "original_value": 8600000.00,
        "status": "running",
        "maintain_cycle_days": 90,
        "owner_name": "设备主管",
        "purchase_date": date(2022, 6, 18),
        "commission_date": date(2022, 9, 1),
        "last_maintain_date": date(2026, 8, 20),
        "next_maintain_date": date(2026, 11, 18),
        "run_hours": 1820.50,
    },
    {
        "equipment_no": "EQ-WT-002",
        "name": "2 号高速风洞",
        "category": "wind_tunnel",
        "model": "WT-H2",
        "spec": "试验段 1.2m × 1.2m，最大风速 120 m/s",
        "workshop": "结构试验车间",
        "location": "试验楼 B2",
        "original_value": 12400000.00,
        "status": "maintenance",
        "maintain_cycle_days": 60,
        "owner_name": "设备主管",
        "purchase_date": date(2021, 11, 5),
        "commission_date": date(2022, 2, 20),
        "last_maintain_date": date(2026, 9, 25),
        "next_maintain_date": date(2026, 11, 24),
        "run_hours": 2410.00,
    },
    {
        "equipment_no": "EQ-CFD-001",
        "name": "CFD 计算集群",
        "category": "cfd",
        "model": "CL-512",
        "spec": "512 核并行，节点 8 台，内存 2TB",
        "workshop": "仿真计算中心",
        "location": "数据机房 3F",
        "original_value": 3200000.00,
        "status": "running",
        "maintain_cycle_days": 180,
        "owner_name": "仿真平台主管",
        "purchase_date": date(2023, 3, 10),
        "commission_date": date(2023, 5, 8),
        "last_maintain_date": date(2026, 6, 12),
        "next_maintain_date": date(2026, 12, 9),
        "run_hours": 5210.75,
    },
    {
        "equipment_no": "EQ-MC-001",
        "name": "五轴联动加工中心",
        "category": "machining",
        "model": "MC-5AX",
        "spec": "行程 800×600×500，定位精度 ±0.005mm",
        "workshop": "机加车间",
        "location": "机加厂房 A 区",
        "original_value": 1800000.00,
        "status": "running",
        "maintain_cycle_days": 30,
        "owner_name": "机加车间主管",
        "purchase_date": date(2023, 8, 22),
        "commission_date": date(2023, 10, 6),
        "last_maintain_date": date(2026, 11, 8),
        "next_maintain_date": date(2026, 12, 8),
        "run_hours": 3660.25,
    },
    {
        "equipment_no": "EQ-MC-002",
        "name": "数控立式加工中心",
        "category": "machining",
        "model": "MC-V3",
        "spec": "行程 600×400×350，主轴转速 12000 r/min",
        "workshop": "机加车间",
        "location": "机加厂房 A 区",
        "original_value": 960000.00,
        "status": "idle",
        "maintain_cycle_days": 30,
        "owner_name": "机加车间主管",
        "purchase_date": date(2024, 1, 15),
        "commission_date": date(2024, 3, 1),
        "last_maintain_date": date(2026, 10, 30),
        "next_maintain_date": date(2026, 11, 29),
        "run_hours": 1420.00,
    },
    {
        "equipment_no": "EQ-MC-003",
        "name": "数控车床",
        "category": "machining",
        "model": "TL-25",
        "spec": "最大回转直径 500mm，最大加工长度 1000mm",
        "workshop": "机加车间",
        "location": "机加厂房 B 区",
        "original_value": 680000.00,
        "status": "fault",
        "maintain_cycle_days": 45,
        "owner_name": "机加车间主管",
        "purchase_date": date(2022, 12, 9),
        "commission_date": date(2023, 1, 16),
        "last_maintain_date": date(2026, 10, 5),
        "next_maintain_date": date(2026, 11, 19),
        "run_hours": 2980.40,
    },
    {
        "equipment_no": "EQ-TS-001",
        "name": "振动测试台",
        "category": "test",
        "model": "VT-200",
        "spec": "推力 200kN，频率 0.5~5000Hz",
        "workshop": "环境试验室",
        "location": "试验楼 1F",
        "original_value": 1250000.00,
        "status": "running",
        "maintain_cycle_days": 90,
        "owner_name": "试验室主管",
        "purchase_date": date(2023, 5, 27),
        "commission_date": date(2023, 8, 14),
        "last_maintain_date": date(2026, 9, 15),
        "next_maintain_date": date(2026, 12, 14),
        "run_hours": 1980.80,
    },
    {
        "equipment_no": "EQ-TS-002",
        "name": "热环境试验箱",
        "category": "test",
        "model": "CT-600",
        "spec": "温度 -70℃~150℃，容积 600L",
        "workshop": "环境试验室",
        "location": "试验楼 1F",
        "original_value": 480000.00,
        "status": "idle",
        "maintain_cycle_days": 120,
        "owner_name": "试验室主管",
        "purchase_date": date(2024, 4, 8),
        "commission_date": date(2024, 6, 12),
        "last_maintain_date": date(2026, 8, 1),
        "next_maintain_date": date(2026, 11, 30),
        "run_hours": 860.00,
    },
]

# 预警样例：1 条未关闭（保养逾期）+ 1 条已关闭（能耗异常，已处理）
_ALERTS: list[dict] = [
    {
        "sample_no": "YJS0001",
        "equipment_no": "EQ-MC-003",
        "rule_type": "maintain_overdue",
        "level": "warning",
        "title": "数控车床 保养逾期",
        "content": "设备下次保养日期已过，保养工单尚未关闭，请联系机加车间主管安排处理。",
        "status": "open",
        "handler_name": "",
        "handle_result": "",
        "days_ago": 3,
    },
    {
        "sample_no": "YJS0002",
        "equipment_no": "EQ-CFD-001",
        "rule_type": "energy_abnormal",
        "level": "warning",
        "title": "CFD 计算集群 能耗异常",
        "content": "集群单日用电超过近 30 天均值 1.5 倍，疑似节点负载不均或散热异常。",
        "status": "closed",
        "handler_name": "仿真平台主管",
        "handle_result": "已核查机柜散热风道，清理进风口滤网后单日能耗回落至均值区间。",
        "days_ago": 12,
    },
]


def _metric_row(eq: Equipment, stat_date: date, rng: random.Random) -> EquipmentMetric:
    """按设备基准运行强度生成一天的能耗 / 工时样例。"""
    base_run = rng.uniform(4.0, 11.0)
    if eq.status == "idle":
        base_run = rng.uniform(0.0, 2.5)
    elif eq.status == "fault":
        base_run = rng.uniform(0.0, 3.5)
    elif eq.status == "maintenance":
        base_run = rng.uniform(0.0, 1.5)

    run_hours = round(base_run, 2)
    downtime = round(rng.uniform(0.0, 1.8), 2)
    # 大型设备能耗高于小型设备；按类别给基线
    energy_base = {
        "wind_tunnel": 420.0,
        "cfd": 980.0,
        "machining": 160.0,
        "test": 95.0,
        "other": 60.0,
    }.get(eq.category, 80.0)
    energy = round(energy_base * (0.35 + run_hours / 10.0) * rng.uniform(0.88, 1.18), 2)
    output = round(max(run_hours, 0.0) * rng.uniform(0.6, 1.4), 2)
    shift = "day" if stat_date.day % 5 else "night"
    source = "schedule" if stat_date.day % 4 else "manual"
    return EquipmentMetric(
        equipment_id=eq.id,
        equipment_no=eq.equipment_no,
        equipment_name=eq.name,
        stat_date=stat_date,
        shift=shift,
        run_hours=run_hours,
        downtime_hours=downtime,
        energy=energy,
        output_qty=output,
        source=source,
        remark="",
    )


def import_equipment(db: Session) -> int:
    """导入 B6 设备台账样例数据（幂等）。返回本次新增的设备台数。"""
    rng = random.Random(_RNG_SEED)
    today = date.today()
    created = 0

    existing = {
        no for (no,) in db.execute(select(Equipment.equipment_no).where(Equipment.deleted == 0)).all()
    }

    new_eqs: list[Equipment] = []
    for spec in _EQUIPMENTS:
        no = spec["equipment_no"]
        if no in existing:
            continue
        eq = Equipment(
            equipment_no=no,
            name=spec["name"],
            category=spec["category"],
            model=spec["model"],
            spec=spec["spec"],
            workshop=spec["workshop"],
            location=spec["location"],
            vendor_id=None,
            vendor_name="",
            purchase_date=spec["purchase_date"],
            commission_date=spec["commission_date"],
            original_value=spec["original_value"],
            status=spec["status"],
            owner_id=None,
            owner_name=spec["owner_name"],
            dept_id=None,
            dept_name="",
            maintain_cycle_days=spec["maintain_cycle_days"],
            last_maintain_date=spec["last_maintain_date"],
            next_maintain_date=spec["next_maintain_date"],
            run_hours=spec["run_hours"],
            remark="",
        )
        db.add(eq)
        new_eqs.append(eq)
        existing.add(no)
        created += 1

    db.flush()

    # 能耗样例：每台设备最近 _METRIC_DAYS 天各一条
    for eq in new_eqs:
        for offset in range(_METRIC_DAYS - 1, -1, -1):
            db.add(_metric_row(eq, today - timedelta(days=offset), rng))

    db.flush()

    # 预警样例
    for spec in _ALERTS:
        eq = db.scalar(select(Equipment).where(Equipment.equipment_no == spec["equipment_no"]).limit(1))
        if eq is None:
            continue
        already = db.scalar(
            select(EquipmentAlert.id)
            .where(
                EquipmentAlert.equipment_no == spec["equipment_no"],
                EquipmentAlert.rule_type == spec["rule_type"],
                EquipmentAlert.deleted == 0,
            )
            .limit(1)
        )
        if already is not None:
            continue
        triggered = datetime.now() - timedelta(days=spec["days_ago"])
        alert = EquipmentAlert(
            alert_no=spec["sample_no"],
            equipment_id=eq.id,
            equipment_no=eq.equipment_no,
            equipment_name=eq.name,
            rule_type=spec["rule_type"],
            level=spec["level"],
            title=spec["title"],
            content=spec["content"],
            status=spec["status"],
            triggered_at=triggered,
            handler_id=None,
            handler_name=spec["handler_name"],
            handled_at=triggered + timedelta(hours=6) if spec["status"] == "closed" else None,
            handle_result=spec["handle_result"],
            remark="",
        )
        db.add(alert)

    db.flush()
    return created


__all__ = ["import_equipment"]
