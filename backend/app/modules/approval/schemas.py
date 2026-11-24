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
    node_type: str = Field("approval", pattern="^(approval|condition|cc|executor)$")
    sign_mode: str = Field("or", pattern="^(or|and|sequential)$")
    approver_type: str = Field(
        "USER",
        pattern="^(USER|ROLE|DEPT_LEADER|PARENT_DEPT_LEADER|SUPERVISOR_CHAIN|FORM_USER|FORM_ROLE|FORM_DEPT_LEADER)$",
    )
    approver_value: str = Field(
        "", max_length=64, description="审批人取值：USER=用户ID，ROLE=角色code，FORM_*=流程变量名"
    )
    approver_name: str = Field("", max_length=128)
    chain_levels: int | None = Field(None, ge=0, le=20, description="SUPERVISOR_CHAIN 级数（空/0=到根）")
    branches: list[BranchIn] | None = None
    default_seq: int | None = Field(None, ge=1)
    field_permissions: dict[str, str] | None = Field(
        None, description="该节点对表单字段的权限：{字段key: editable|viewonly|hidden}"
    )


class DefinitionIn(CamelModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    biz_type: str = Field(..., min_length=1, max_length=32)
    enabled: int = 1
    remark: str = Field("", max_length=255)
    variables_schema: dict[str, Any] | None = None
    options: dict[str, Any] | None = Field(
        None,
        description=(
            "流程通用选项：commentRequired 意见必填 / commentSignRequired 意见需签名 / "
            "allowAddSign 允许加签 / allowWithdrawAfterApproved 通过后可撤销 / "
            "allowModifyFlow 审批人可改流程 / allowModifyCc 审批人可改抄送 / "
            "executorCommentRequired 办理意见必填 / executorCanModify 办理人可修改 / "
            "allowProxySubmit 允许代提交 / detailTablePermission 明细表权限控制"
        ),
    )
    process_graph: dict[str, Any] | None = Field(
        None, description="LogicFlow 图（设计器提交时原样存储，保留布局；缺省由节点行自动生成）"
    )
    nodes: list[NodeIn] = Field(default_factory=list)


class FlowSuggestIn(CamelModel):
    """AI 审批链建议入参：金额/分类可选，供 AI 参考节点层级。"""

    biz_type: str = Field(..., min_length=1, max_length=32)
    name: str = Field("", max_length=64)
    amount: float | None = Field(None, ge=0)
    category: str = Field("", max_length=64)


class PreviewIn(CamelModel):
    """按 variables 预览分支走向；nodes 缺省时按已保存定义预览，传入则预览画布草稿。"""

    definition_code: str = Field("", max_length=64)
    variables: dict[str, Any] = Field(default_factory=dict)
    nodes: list[NodeIn] | None = None
