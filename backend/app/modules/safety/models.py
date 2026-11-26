"""安全巡检域（B8 / CSV 24）模型。

表前缀 `saf_`：
- `saf_inspection_plan` 巡检计划（周期 / 巡检项清单 / 负责人 / 下次巡检日期）
- `saf_inspection`      巡检记录（逐项结果 / 异常项数 / 状态：草稿·已提交·已闭环）
- `saf_hazard`          隐患（整改 / 验证 / 关闭闭环）

三张表都继承 `BaseModel`（有 `deleted` 逻辑删除），删除动作走全站统一回收站
（`app/common/recycle.py::soft_delete`）。
"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class SafetyInspectionPlan(BaseModel):
    """巡检计划 —— 规定「查什么、谁查、多久查一次」。"""

    __tablename__ = "saf_inspection_plan"

    plan_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="计划编号")
    name: Mapped[str] = mapped_column(String(128), default="", comment="计划名称")
    plan_type: Mapped[str] = mapped_column(
        String(16), default="daily", index=True, comment="daily/weekly/monthly/special"
    )
    target_area: Mapped[str] = mapped_column(String(128), default="", comment="巡检区域 / 对象")
    check_items: Mapped[str] = mapped_column(Text, default="", comment="巡检项清单（JSON 数组字符串）")
    cycle_days: Mapped[int] = mapped_column(Integer, default=1, comment="周期天数")
    next_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True, comment="下次巡检日期")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="负责人 id")
    owner_name: Mapped[str] = mapped_column(String(64), default="", comment="负责人姓名")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="归属部门 id")
    dept_name: Mapped[str] = mapped_column(String(128), default="", comment="归属部门")
    status: Mapped[str] = mapped_column(String(16), default="active", index=True, comment="active/paused/finished")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class SafetyInspection(BaseModel):
    """巡检记录 —— 一次实际巡检的逐项结果。"""

    __tablename__ = "saf_inspection"

    record_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="记录编号")
    plan_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="关联计划 id")
    plan_name: Mapped[str] = mapped_column(String(128), default="", comment="关联计划名称")
    area: Mapped[str] = mapped_column(String(128), default="", comment="巡检区域")
    inspect_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True, comment="巡检日期")
    inspector_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="巡检人 id")
    inspector_name: Mapped[str] = mapped_column(String(64), default="", comment="巡检人姓名")
    result: Mapped[str] = mapped_column(String(16), default="normal", index=True, comment="normal/abnormal")
    abnormal_count: Mapped[int] = mapped_column(Integer, default=0, comment="异常项数")
    items_json: Mapped[str] = mapped_column(Text, default="", comment="逐项结果（JSON 数组字符串）")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True, comment="draft/submitted/closed")
    summary: Mapped[str] = mapped_column(String(500), default="", comment="巡检小结")
    remark: Mapped[str] = mapped_column(String(500), default="", comment="备注")


class SafetyHazard(BaseModel):
    """隐患 —— 巡检发现或手工上报，整改 → 验证 → 关闭闭环。"""

    __tablename__ = "saf_hazard"

    hazard_no: Mapped[str] = mapped_column(String(32), unique=True, index=True, comment="隐患编号")
    inspection_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="来源巡检记录 id")
    record_no: Mapped[str] = mapped_column(String(32), default="", comment="来源巡检记录编号")
    source: Mapped[str] = mapped_column(String(16), default="inspection", comment="inspection/manual")
    description: Mapped[str] = mapped_column(String(500), default="", comment="隐患描述")
    level: Mapped[str] = mapped_column(String(16), default="medium", index=True, comment="low/medium/high/critical")
    status: Mapped[str] = mapped_column(
        String(16), default="open", index=True, comment="open/rectifying/verified/closed"
    )
    responsible_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="责任人 id")
    responsible_name: Mapped[str] = mapped_column(String(64), default="", comment="责任人姓名")
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True, index=True, comment="整改期限")
    found_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), comment="发现时间")
    measure: Mapped[str] = mapped_column(String(500), default="", comment="整改措施")
    rectified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="整改完成时间")
    rectified_by_name: Mapped[str] = mapped_column(String(64), default="", comment="整改人姓名")
    verify_result: Mapped[str] = mapped_column(String(500), default="", comment="验证结论")
    verify_by_name: Mapped[str] = mapped_column(String(64), default="", comment="验证人姓名")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="验证时间")
    remark: Mapped[str] = mapped_column(String(255), default="", comment="备注")
