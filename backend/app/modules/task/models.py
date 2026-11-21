"""任务 4 表：task_task / task_item / task_sample / task_sample_flow。"""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class Task(BaseModel):
    """状态机：draft → in_progress → finished → settled；流程态 approving/rejected；终态 stopped。"""

    __tablename__ = "task_task"

    task_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="任务编号 RW...（提交审批时发放，草稿不占号）"
    )
    task_name: Mapped[str] = mapped_column(String(255), index=True)
    task_type: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 task_type")
    contract_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    contract_no: Mapped[str] = mapped_column(String(32), default="", comment="合同号冗余")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(128), default="", comment="客户名冗余")
    biz_block: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 biz_block")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    dept_name: Mapped[str] = mapped_column(String(64), default="")
    owner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="负责人")
    owner_name: Mapped[str] = mapped_column(String(64), default="")
    content: Mapped[str | None] = mapped_column(Text, nullable=True, comment="试验/工作内容")
    party_system: Mapped[str] = mapped_column(String(64), default="", comment="外部系统")
    receiver: Mapped[str] = mapped_column(String(64), default="", comment="接样人")
    receiver_unit: Mapped[str] = mapped_column(String(128), default="", comment="受检单位")
    plan_finish_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    # --- B5 任务字段扩展（CSV 18–21）---
    plan_start_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="计划开始日期")
    duration_hours: Mapped[float] = mapped_column(
        Numeric(10, 2), default=8, comment="预计工时（小时），排程用"
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="进度百分比 0-100")
    priority: Mapped[int] = mapped_column(Integer, default=5, comment="优先级 1(最高)~9(最低)")
    role_group: Mapped[str] = mapped_column(
        String(32), default="", index=True, comment="角色分组（字典 task_role_group）：sim/model/test/outsource"
    )
    process_stage: Mapped[str] = mapped_column(String(32), default="", comment="当前工序编码")
    # CFD 专属字段（CSV 19）
    mesh_count: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="网格数（万单元）")
    solver: Mapped[str] = mapped_column(String(32), default="", comment="求解器")
    compute_resource: Mapped[str] = mapped_column(String(64), default="", comment="算力资源池")
    compute_cores: Mapped[int] = mapped_column(Integer, default=0, comment="核数")
    compute_nodes: Mapped[int] = mapped_column(Integer, default=0, comment="节点数")
    items = relationship(
        "TaskItem", foreign_keys="TaskItem.task_id", cascade="all, delete-orphan", lazy="selectin"
    )
    samples = relationship(
        "TaskSample", foreign_keys="TaskSample.task_id", cascade="all, delete-orphan", lazy="selectin"
    )
    processes = relationship(
        "TaskProcess", foreign_keys="TaskProcess.task_id", cascade="all, delete-orphan", lazy="selectin"
    )


class TaskProcess(BaseModel):
    """工序流转（B5 CSV 19）：油泥 / CNC / 表面处理 等加工工序的流转记录。

    状态机：pending → running → done（可 skipped 跳过）；同一任务同一时刻只有一个
    `is_current=1` 的工序，用于在任务列表上直接展示"当前处于哪道工序"。
    """

    __tablename__ = "task_process"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1, comment="工序序号")
    process_code: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 task_process")
    process_name: Mapped[str] = mapped_column(String(64), default="", comment="工序名称冗余")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True, comment="pending/running/done/skipped"
    )
    is_current: Mapped[int] = mapped_column(Integer, default=0, comment="是否当前工序")
    planned_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    actual_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    dept_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    dept_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")


class TaskAssignment(BaseModel):
    """任务分配（B5 CSV 20）：人 / 机 / 料 / 法 / 环 / 测 / 安 七维资源分配。

    `dimension` 取值：person 人员 · equipment 设备 · material 物料 ·
    method 方法 · env 环境 · test 试验条件 · safety 安全措施 · vehicle 样车。
    排程（production 域）会读取本表的 equipment / person / vehicle（时段独占）
    与 material（数量占用）维度做资源占用。
    """

    __tablename__ = "task_assignment"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(16), default="person", index=True)
    resource_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    resource_code: Mapped[str] = mapped_column(String(64), default="")
    resource_name: Mapped[str] = mapped_column(String(128), default="")
    qty: Mapped[float] = mapped_column(Numeric(12, 2), default=0, comment="需求量")
    unit: Mapped[str] = mapped_column(String(16), default="")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True, comment="pending/allocated/confirmed/rejected"
    )
    assigner_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    assigner_name: Mapped[str] = mapped_column(String(64), default="")
    planned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remark: Mapped[str] = mapped_column(String(500), default="")


class TaskTrace(BaseModel):
    """任务全过程追溯（B5 CSV 19）：输入 → 报告输出 / 样车归还 / 模型车发运。

    `node_code` 取值：input 输入 · output_report 报告输出 · vehicle_return 样车归还 ·
    model_ship 模型车发运 · accept 验收 · settle 结算。
    """

    __tablename__ = "task_trace"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    node_code: Mapped[str] = mapped_column(String(32), default="input", index=True)
    node_name: Mapped[str] = mapped_column(String(64), default="")
    seq: Mapped[int] = mapped_column(Integer, default=1)
    happen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ref_no: Mapped[str] = mapped_column(String(64), default="", comment="关联单号（报告号 / 样车 VIN）")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")


class TaskItem(BaseModel):
    """任务子条目（报告挂 need_report）。"""

    __tablename__ = "task_item"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(32), default="", comment="条目编号")
    name: Mapped[str] = mapped_column(String(128), default="")
    std: Mapped[str] = mapped_column(String(128), default="", comment="依据标准")
    dept: Mapped[str] = mapped_column(String(64), default="", comment="试验室")
    inspector: Mapped[str] = mapped_column(String(64), default="", comment="试验人")
    qty: Mapped[int] = mapped_column(Integer, default=1, comment="数量")
    settle_type: Mapped[str] = mapped_column(String(32), default="", comment="结算方式")
    need_report: Mapped[int] = mapped_column(Integer, default=0)
    report_no: Mapped[str] = mapped_column(String(32), default="", comment="报告编号 BG...")
    report_status: Mapped[str] = mapped_column(String(16), default="", comment="报告状态")


class TaskSample(BaseModel):
    """样品：编号=任务号-01；in_stock: in/out。"""

    __tablename__ = "task_sample"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    sample_no: Mapped[str | None] = mapped_column(
        String(64), unique=True, index=True, nullable=True, comment="编号=任务号-01（随任务提交发放）"
    )
    name: Mapped[str] = mapped_column(String(128), default="")
    model: Mapped[str] = mapped_column(String(64), default="", comment="型号")
    vin: Mapped[str] = mapped_column(String(64), default="")
    vehicle_type: Mapped[str] = mapped_column(String(64), default="", comment="车型")
    sample_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    in_stock: Mapped[str] = mapped_column(String(8), default="in", comment="in=在库 out=出库")


class TaskSampleFlow(BaseModel):
    """样品出入库流水。"""

    __tablename__ = "task_sample_flow"

    sample_id: Mapped[int] = mapped_column(BigInteger, index=True)
    task_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(8), comment="in/out")
    operator_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    remark: Mapped[str] = mapped_column(String(255), default="")


class TaskProgressLog(BaseModel):
    """任务进度记录：拍照/AI 分析草稿必须人工确认后经 POST 落库（source=ai|manual）。"""

    __tablename__ = "task_progress_log"

    task_id: Mapped[int] = mapped_column(ForeignKey("task_task.id"), index=True)
    percent: Mapped[int] = mapped_column(Integer, default=0, comment="完成百分比 0-100")
    note: Mapped[str] = mapped_column(Text, default="", comment="进度描述")
    image_path: Mapped[str] = mapped_column(String(255), default="", comment="现场照片（相对 upload_dir）")
    source: Mapped[str] = mapped_column(String(8), default="manual", comment="ai/manual")
    operator_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")


class TaskEntrust(BaseModel):
    """在线任务委托单（B2）：客户基于合同下单，业务经理可代提交。

    状态机：draft → submitted → accepted / rejected；accepted → dispatched → closed。
    submitted 由门户客户提交或业务经理代提交产生；accepted 表示客户经理已受理；
    dispatched 表示已按委托单生成任务草稿（task_id 回写）。
    """

    __tablename__ = "task_entrust"

    entrust_no: Mapped[str | None] = mapped_column(
        String(32), unique=True, index=True, nullable=True, comment="委托单号 WT...（受理时发放）"
    )
    title: Mapped[str] = mapped_column(String(255), index=True, comment="委托标题")
    entrust_type: Mapped[str] = mapped_column(
        String(32), default="", index=True, comment="字典 entrust_type：sim/model/test/outsource"
    )
    contract_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    contract_no: Mapped[str] = mapped_column(String(32), default="", comment="合同号冗余")
    customer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    biz_block: Mapped[str] = mapped_column(String(32), default="", index=True, comment="字典 biz_block")
    source: Mapped[str] = mapped_column(
        String(16), default="portal", index=True, comment="portal 客户自助 / staff 业务代提交"
    )
    applicant_type: Mapped[str] = mapped_column(String(16), default="portal", comment="portal 客户 / internal 员工")
    applicant_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True, comment="申请人 id")
    applicant_name: Mapped[str] = mapped_column(String(64), default="")
    applicant_phone: Mapped[str] = mapped_column(String(32), default="")
    requirement: Mapped[str | None] = mapped_column(Text, nullable=True, comment="技术要求 / 需求描述")
    sample_desc: Mapped[str] = mapped_column(String(500), default="", comment="送样 / 样车说明")
    plan_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    plan_end_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="期望完成日期")
    priority: Mapped[str] = mapped_column(String(16), default="normal", comment="normal / urgent")
    amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True, comment="预估金额")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    handler_id: Mapped[int | None] = mapped_column(BigInteger, index=True, comment="受理人（客户经理）")
    handler_name: Mapped[str] = mapped_column(String(64), default="")
    biz_owner_id: Mapped[int | None] = mapped_column(BigInteger, index=True, comment="业务负责人（受理后抄送）")
    biz_owner_name: Mapped[str] = mapped_column(String(64), default="")
    review_by: Mapped[int | None] = mapped_column(BigInteger)
    review_name: Mapped[str] = mapped_column(String(64), default="")
    review_at: Mapped[datetime | None] = mapped_column(nullable=True)
    review_comment: Mapped[str] = mapped_column(String(500), default="")
    task_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="生成的任务 task_task.id"
    )
    task_no: Mapped[str] = mapped_column(String(32), default="")
    remark: Mapped[str] = mapped_column(String(500), default="")
    items = relationship(
        "TaskEntrustItem", foreign_keys="TaskEntrustItem.entrust_id", cascade="all, delete-orphan", lazy="selectin"
    )


class TaskEntrustItem(BaseModel):
    """委托明细行：受理后转为任务条目（试验项目 / 依据标准 / 数量 / 报告要求）。"""

    __tablename__ = "task_entrust_item"

    entrust_id: Mapped[int] = mapped_column(ForeignKey("task_entrust.id"), index=True)
    item_code: Mapped[str] = mapped_column(String(32), default="", comment="条目编号")
    name: Mapped[str] = mapped_column(String(128), default="", comment="试验项目")
    std: Mapped[str] = mapped_column(String(128), default="", comment="依据标准")
    qty: Mapped[int] = mapped_column(Integer, default=1, comment="数量 / 台次")
    need_report: Mapped[int] = mapped_column(Integer, default=1, comment="是否出报告")
    report_type: Mapped[str] = mapped_column(String(32), default="", comment="报告类型")
    remark: Mapped[str] = mapped_column(String(255), default="")
