"""审批引擎 5 表：definition / node / instance / task / record。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.common.models import BaseModel


class ApprovalDefinition(BaseModel):
    """流程定义（按业务注册，如 contract_approve）。"""

    __tablename__ = "approval_definition"
    __table_args__ = (UniqueConstraint("code"),)

    code: Mapped[str] = mapped_column(String(64), index=True, comment="流程 Key")
    name: Mapped[str] = mapped_column(String(64), comment="流程名称")
    biz_type: Mapped[str] = mapped_column(String(32), index=True, comment="contract/report/...")
    enabled: Mapped[int] = mapped_column(Integer, default=1)
    remark: Mapped[str] = mapped_column(String(255), default="")

    nodes = relationship(
        "ApprovalNode",
        foreign_keys="ApprovalNode.definition_id",
        cascade="all, delete-orphan",
        order_by="ApprovalNode.seq",
        lazy="selectin",
    )


class ApprovalNode(BaseModel):
    """顺序节点：approver_type ∈ USER | ROLE；同节点或签（任一通过即过）。"""

    __tablename__ = "approval_node"
    __table_args__ = (UniqueConstraint("definition_id", "seq"),)

    definition_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_definition.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1, comment="节点序号，从 1 起")
    node_name: Mapped[str] = mapped_column(String(64), default="", comment="节点名（如 部门审批）")
    approver_type: Mapped[str] = mapped_column(String(16), default="USER", comment="USER/ROLE")
    approver_value: Mapped[str] = mapped_column(String(64), default="", comment="用户ID/角色code，逗号分隔")
    approver_name: Mapped[str] = mapped_column(String(128), default="", comment="展示名（冗余）")


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
    current_seq: Mapped[int] = mapped_column(Integer, default=1, comment="当前节点序号")
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
    """待办：节点上每个审批人一条（或签）。"""

    __tablename__ = "approval_task"

    instance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_instance.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=1)
    node_name: Mapped[str] = mapped_column(String(64), default="")
    assignee_id: Mapped[int] = mapped_column(BigInteger, index=True)
    assignee_name: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(
        String(16), default="pending", index=True, comment="pending/agreed/rejected/transferred/cancelled"
    )
    task_kind: Mapped[str] = mapped_column(String(16), default="sign", comment="sign/add_sign")
    comment: Mapped[str] = mapped_column(String(500), default="")
    acted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acted_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="实际处理人（转办场景）")


class ApprovalRecord(BaseModel):
    """意见时间线（start/agree/reject/withdraw/add_sign/transfer）。"""

    __tablename__ = "approval_record"

    instance_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("approval_instance.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer, default=0)
    node_name: Mapped[str] = mapped_column(String(64), default="")
    action: Mapped[str] = mapped_column(String(16), index=True)
    operator_id: Mapped[int] = mapped_column(BigInteger, index=True)
    operator_name: Mapped[str] = mapped_column(String(64), default="")
    comment: Mapped[str] = mapped_column(String(500), default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
