"""B6 设备台账 / 设备能耗采集 / 设备预警（B6 CSV 67-69）。

三张表（`ast_` 前缀，继承 `app/common/models.py::BaseModel`）：

- `ast_equipment`        设备台账（编号 / 类别 / 车间 / 状态 / 保养周期 / 累计工时）
- `ast_equipment_metric` 能耗与运行数据（按日 + 班次采集）
- `ast_equipment_alert`  设备预警（保养逾期 / 能耗异常 / 利用率偏低 / 故障 / 状态异常）

统一框架（不新建组织 / 公司 / 权限表）：
- 部门 → `sys_dept`（`dept_id` + `dept_name` 冗余）
- 供应商 → `crm_customer`（`vendor_id` + `vendor_name` 冗余）
- 权限 → `sys_menu`（`module:resource:action`，见 seeds/init_data.py::MENU_TREE）
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel

# ---------------- 设备台账 ----------------


class Equipment(BaseModel):
    """设备台账。

    状态：idle 闲置 / running 运行中 / maintenance 维护中 / fault 故障 / scrapped 已报废。
    """

    __tablename__ = "ast_equipment"

    equipment_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="设备编号")
    name: Mapped[str] = mapped_column(String(128), index=True, comment="设备名称")
    category: Mapped[str] = mapped_column(
        String(32), default="other", index=True, comment="设备类别 wind_tunnel/cfd/machining/test/other"
    )
    model: Mapped[str] = mapped_column(String(64), default="", comment="型号")
    spec: Mapped[str] = mapped_column(String(255), default="", comment="规格")
    workshop: Mapped[str] = mapped_column(String(64), default="", index=True, comment="所属车间/区域")
    location: Mapped[str] = mapped_column(String(128), default="", comment="安装位置")
    vendor_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="供应商 crm_customer.id"
    )
    vendor_name: Mapped[str] = mapped_column(String(128), default="", comment="供应商名冗余")
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="购置日期")
    commission_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="投产日期")
    original_value: Mapped[float] = mapped_column(Numeric(14, 2), default=0, comment="原值")
    status: Mapped[str] = mapped_column(
        String(16), default="idle", index=True, comment="idle/running/maintenance/fault/scrapped"
    )
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="责任人 sys_user.id")
    owner_name: Mapped[str] = mapped_column(String(64), default="", comment="责任人姓名")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="使用部门 sys_dept.id")
    dept_name: Mapped[str] = mapped_column(String(128), default="", comment="使用部门名冗余")
    maintain_cycle_days: Mapped[int] = mapped_column(Integer, default=0, comment="保养周期（天，0=不启用）")
    last_maintain_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="上次保养日期")
    next_maintain_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True, comment="下次保养日期")
    run_hours: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="累计运行工时")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


# ---------------- 能耗 / 运行数据 ----------------


class EquipmentMetric(BaseModel):
    """设备能耗与运行数据（按日 + 班次采集）。"""

    __tablename__ = "ast_equipment_metric"

    equipment_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="设备 ast_equipment.id")
    equipment_no: Mapped[str] = mapped_column(String(32), default="", comment="设备编号冗余")
    equipment_name: Mapped[str] = mapped_column(String(128), default="", comment="设备名称冗余")
    stat_date: Mapped[date] = mapped_column(Date, index=True, comment="统计日期")
    shift: Mapped[str] = mapped_column(String(16), default="day", comment="班次 morning/day/night")
    run_hours: Mapped[float] = mapped_column(Numeric(10, 2), default=0, comment="运行工时")
    downtime_hours: Mapped[float] = mapped_column(Numeric(10, 2), default=0, comment="停机工时")
    energy: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="能耗 kWh")
    output_qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="产量/台次")
    source: Mapped[str] = mapped_column(String(16), default="manual", comment="来源 manual/schedule")
    remark: Mapped[str] = mapped_column(String(255), default="", comment="备注")


# ---------------- 设备预警 ----------------


class EquipmentAlert(BaseModel):
    """设备预警（扫描生成 + 手工登记）。

    规则类型：maintain_overdue 保养逾期 / energy_abnormal 能耗异常 /
    low_utilization 利用率偏低 / fault 设备故障 / status_abnormal 状态异常。
    状态：open 待处理 / processing 处理中 / closed 已关闭。
    """

    __tablename__ = "ast_equipment_alert"

    alert_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="预警单号")
    equipment_id: Mapped[int] = mapped_column(BigInteger, index=True, comment="设备 ast_equipment.id")
    equipment_no: Mapped[str] = mapped_column(String(32), default="", comment="设备编号冗余")
    equipment_name: Mapped[str] = mapped_column(String(128), default="", comment="设备名称冗余")
    rule_type: Mapped[str] = mapped_column(
        String(32),
        default="status_abnormal",
        index=True,
        comment="maintain_overdue/energy_abnormal/low_utilization/fault/status_abnormal",
    )
    level: Mapped[str] = mapped_column(String(16), default="warning", comment="级别 info/warning/critical")
    title: Mapped[str] = mapped_column(String(128), default="", comment="预警标题")
    content: Mapped[str] = mapped_column(String(500), default="", comment="预警内容")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True, comment="open/processing/closed")
    triggered_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, index=True, comment="触发时间")
    handler_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="处理人 sys_user.id")
    handler_name: Mapped[str] = mapped_column(String(64), default="", comment="处理人姓名")
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="处理时间")
    handle_result: Mapped[str] = mapped_column(String(500), default="", comment="处理结果")
    remark: Mapped[str] = mapped_column(String(255), default="", comment="备注")


__all__ = ["Equipment", "EquipmentMetric", "EquipmentAlert"]
