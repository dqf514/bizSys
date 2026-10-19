"""审批模块入参模型。"""

from typing import Any

from pydantic import Field

from app.core.schemas import CamelModel


class CommentIn(CamelModel):
    comment: str = Field("", max_length=500)


class TransferIn(CamelModel):
    to_user_id: int
    comment: str = Field("", max_length=500)


class AddSignIn(CamelModel):
    approver_id: int
    comment: str = Field("", max_length=500)


class WithdrawIn(CamelModel):
    comment: str = Field("", max_length=500)


class BranchIn(CamelModel):
    """条件分支：expr 结构化表达式 {field, op, value}，命中跳转 target_seq。"""

    expr: dict[str, Any] = Field(default_factory=dict)
    target_seq: int = Field(..., ge=1)


class NodeIn(CamelModel):
    seq: int = Field(1, ge=1)
    node_name: str = Field("", max_length=64)
    node_type: str = Field("approval", pattern="^(approval|condition|cc)$")
    sign_mode: str = Field("or", pattern="^(or|and|sequential)$")
    approver_type: str = Field(
        "USER", pattern="^(USER|ROLE|DEPT_LEADER|PARENT_DEPT_LEADER|SUPERVISOR_CHAIN)$"
    )
    approver_value: str = Field("", max_length=64)
    approver_name: str = Field("", max_length=128)
    chain_levels: int | None = Field(None, ge=0, le=20, description="SUPERVISOR_CHAIN 级数（空/0=到根）")
    branches: list[BranchIn] | None = None
    default_seq: int | None = Field(None, ge=1)


class DefinitionIn(CamelModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    biz_type: str = Field(..., min_length=1, max_length=32)
    enabled: int = 1
    remark: str = Field("", max_length=255)
    variables_schema: dict[str, Any] | None = None
    process_graph: dict[str, Any] | None = Field(
        None, description="LogicFlow 图（设计器提交时原样存储，保留布局；缺省由节点行自动生成）"
    )
    nodes: list[NodeIn] = Field(default_factory=list)


class PreviewIn(CamelModel):
    """按 variables 预览分支走向；nodes 缺省时按已保存定义预览，传入则预览画布草稿。"""

    definition_code: str = Field("", max_length=64)
    variables: dict[str, Any] = Field(default_factory=dict)
    nodes: list[NodeIn] | None = None
