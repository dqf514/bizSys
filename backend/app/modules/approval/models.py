"""审批引擎表：definition / node / instance / task / record / cc / view_state。

F1 工作流引擎合并（对齐 TPCworkflow 语义）：
- definition 增加 process_graph（LogicFlow JSON）与 variables_schema；
- node 增加 node_type（approval/condition/cc）、sign_mode（or/and/sequential）、branches/default_seq；
- instance 增加 variables / current_node_ids；task 增加 node_type / action_meta；
- record 充当只追加时间线，增加 payload；
- 新增 approval_cc（抄送）与 approval_view_state（发起人进度未读水位）。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class ApprovalDefinition(BaseModel):
    """流程定义（按业务注册，如 contract_approve）。

    版本化：同 code 多版本（flow_version 递增）；编辑有进行中实例的定义自动另存新版本，
    老版本保留供存量实例按 definition_id 流转，新发起解析最新启用版本。
    enabled 承担发布状态语义：1=启用 / 0=停用（删除有实例的定义时改为停用）。
    """

    __tablename__ = "approval_definition"
    __table_args__ = (UniqueConstraint("code", "flow_version", "deleted", name="uq_approval_definition_code_version"),)

    code: Mapped[str] = mapped_column(String(64), index=True, comment="流程 Key")
    name: Mapped[str] = mapped_column(String(64), comment="流程名称")
    biz_type: Mapped[str] = mapped_column(String(32), index=True, comment="contract/report/...")
    flow_version: Mapped[int] = mapped_column(Integer, default=1, comment="定义版本号（同 code 递增，从 1 起）")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    remark: Mapped[str] = mapped_column(String(255), default="")
    process_graph: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="LogicFlow 图 JSON（线性定义自动生成等价图）"
    )
    variables_schema: Mapped[str | None] = mapped_column(Text, nullable=True, comment="流程变量声明 JSON")

    nodes = relationship(
        "ApprovalNode",
        foreign_keys="ApprovalNode.definition_id",
        cascade="all, delete-orphan",
        order_by="ApprovalNode.seq",
        lazy="selectin",
    )


class ApprovalNode(BaseModel):
    """流程节点：approval（审批）/ condition（条件分支）/ cc（抄送）。

    - 审批节点 sign_mode ∈ or（任一通过）/ and（全员通过）/ sequential（按序逐个）；
    - approver_type ∈ USER | ROLE；approver_value 逗号分隔；
    - 条件节点用 branches（JSON: [{expr:{field,op,value}, targetSeq}]）+ default_seq 路由；
    - 抄送节点复用 approver_type/approver_value 解析接收人，不产生待办、不阻塞流转。
    """

    __tablename__ = "approval_node"
    __table_args__ = (UniqueConstraint("definition_id", "seq"),)

    definition_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_definition.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1, comment="节点序号，从 1 起")
    node_name: Mapped[str] = mapped_column(String(64), default="", comment="节点名（如 部门审批）")
    node_type: Mapped[str] = mapped_column(String(16), default="approval", comment="approval/condition/cc")
    sign_mode: Mapped[str] = mapped_column(String(16), default="or", comment="or/and/sequential（仅审批节点）")
    approver_type: Mapped[str] = mapped_column(
        String(32), default="USER", comment="USER/ROLE/DEPT_LEADER/PARENT_DEPT_LEADER/SUPERVISOR_CHAIN"
    )
    approver_value: Mapped[str] = mapped_column(
        String(64), default="", comment="用户ID/角色code 逗号分隔；组织类型时为兜底角色code（可空）"
    )
    chain_levels: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="SUPERVISOR_CHAIN 逐级级数（空/0=一直到根部门）"
    )
    approver_name: Mapped[str] = mapped_column(String(128), default="", comment="展示名（冗余）")
    branches: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="条件分支 JSON：[{expr:{field,op,value},targetSeq}]"
    )
    default_seq: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="条件未命中时跳转序号（空=顺序下一节点）"
    )


class ApprovalInstance(BaseModel):
    """审批实例：每 (biz_type, biz_id) 同时最多 1 个 running。"""

    __tablename__ = "approval_instance"

    biz_type: Mapped[str] = mapped_column(String(32), index=True)
    biz_id: Mapped[int] = mapped_column(BigInteger, index=True)
    definition_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    definition_code: Mapped[str] = mapped_column(String(64), default="")
    title: Mapped[str] = mapped_column(String(255), default="", comment="单据标题（快照）")
    status: Mapped[str] = mapped_column(
        String(16), default="running", index=True, comment="running/approved/rejected/withdrawn"
    )
    current_seq: Mapped[int] = mapped_column(Integer, default=1, comment="当前节点序号（线性兜底展示）")
    current_node_ids: Mapped[str | None] = mapped_column(Text, nullable=True, comment="当前节点序号 JSON 数组")
    variables: Mapped[str | None] = mapped_column(Text, nullable=True, comment="流程变量 JSON（发起时注入）")
    initiator_id: Mapped[int] = mapped_column(BigInteger, index=True)
    initiator_name: Mapped[str] = mapped_column(String(64), default="")
    form_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True, comment="业务表单 JSON 快照")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    records = relationship(
        "ApprovalRecord",
        foreign_keys="ApprovalRecord.instance_id",
        cascade="all, delete-orphan",
        order_by="ApprovalRecord.id",
        lazy="selectin",
    )


class ApprovalTask(BaseModel):
    """待办：节点上每个审批人一条；依次签只有队列首人持有 pending。"""

    __tablename__ = "approval_task"

    instance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_instance.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1)
    node_name: Mapped[str] = mapped_column(String(64), default="")
    node_type: Mapped[str] = mapped_column(String(16), default="approval", comment="approval（冗余节点类型）")
    assignee_id: Mapped[int] = mapped_column(BigInteger, index=True)
    assignee_name: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True, comment="pending/agreed/rejected/transferred/cancelled"
    )
    task_kind: Mapped[str] = mapped_column(String(16), default="sign", comment="sign/add_sign")
    action_meta: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="依次队列 sequential_queue/index、加签来源等 JSON"
    )
    comment: Mapped[str] = mapped_column(String(500), default="")
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acted_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="实际处理人（转办场景）")


class ApprovalRecord(BaseModel):
    """时间线（只追加）：start/agree/reject/withdraw/add_sign/transfer/cc/auto_pass。"""

    __tablename__ = "approval_record"

    instance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_instance.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    node_name: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(16), index=True)
    operator_id: Mapped[int] = mapped_column(BigInteger, index=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    comment: Mapped[str] = mapped_column(String(500), default="")
    payload: Mapped[str | None] = mapped_column(Text, nullable=True, comment="动作附带数据 JSON")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class ApprovalCc(BaseModel):
    """抄送：cc 节点解析出的接收人各一条，不阻塞流转。"""

    __tablename__ = "approval_cc"

    instance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_instance.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0, comment="产生抄送的节点序号")
    node_name: Mapped[str] = mapped_column(String(64), default="")
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_name: Mapped[str] = mapped_column(String(64), default="")
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="已读时间（空=未读）")


class ApprovalViewState(BaseModel):
    """发起人进度未读水位：last_seen_at 之后的时间线条目计入未读角标。"""

    __tablename__ = "approval_view_state"
    __table_args__ = (UniqueConstraint("user_id", "instance_id", name="uq_approval_view_state_user_instance"),)

    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    instance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_instance.id"), index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
