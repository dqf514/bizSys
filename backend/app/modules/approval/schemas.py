"""审批模块入参模型。"""

from pydantic import BaseModel, Field


class CommentIn(BaseModel):
    comment: str = Field("", max_length=500)


class TransferIn(BaseModel):
    to_user_id: int
    comment: str = Field("", max_length=500)


class AddSignIn(BaseModel):
    approver_id: int
    comment: str = Field("", max_length=500)


class WithdrawIn(BaseModel):
    comment: str = Field("", max_length=500)


class NodeIn(BaseModel):
    seq: int = Field(1, ge=1)
    node_name: str = Field("", max_length=64)
    approver_type: str = Field("USER", pattern="^(USER|ROLE)$")
    approver_value: str = Field("", max_length=64)
    approver_name: str = Field("", max_length=128)


class DefinitionIn(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    biz_type: str = Field(..., min_length=1, max_length=32)
    enabled: int = 1
    remark: str = Field("", max_length=255)
    nodes: list[NodeIn] = Field(default_factory=list)
