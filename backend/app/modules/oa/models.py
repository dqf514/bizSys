"""OA 表单与单据表：oa_form（模板，key+form_version 版本化）/ oa_instance（单据，快照 + 流程关联）。

- oa_form.schema_json：{"fields": [{key,label,type,required,options,placeholder,maxlength,exposeVariable}]}；
- oa_instance.status 跟随审批引擎：running/approved/rejected/withdrawn/terminated（直通单提交即 approved）；
- form/schema 均快照进实例，模板后续改版不影响历史单据。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class OaForm(BaseModel):
    """OA 表单模板（draft/published/disabled；发布后改版走 form_version+1 新草稿）。"""

    __tablename__ = "oa_form"
    # deleted 入唯一键：软删行不阻塞同 key+version 重建
    __table_args__ = (UniqueConstraint("key", "form_version", "deleted", name="uq_oa_form_key_version"),)

    key: Mapped[str] = mapped_column(String(64), index=True, comment="表单标识")
    name: Mapped[str] = mapped_column(String(128), comment="表单名称")
    form_version: Mapped[int] = mapped_column(Integer, default=1, comment="表单版本（BaseModel.version 是乐观锁）")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True, comment="draft/published/disabled")
    category: Mapped[str] = mapped_column(String(32), default="", index=True, comment="分类（字典 oa_category）")
    icon: Mapped[str] = mapped_column(String(64), default="")
    sort: Mapped[int] = mapped_column(Integer, default=0)
    schema_json: Mapped[str] = mapped_column(Text, nullable=True, comment="字段定义 JSON")
    flow_definition_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, comment="绑定 approval_definition.id；空=提交直通"
    )
    description: Mapped[str] = mapped_column(String(512), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class OaInstance(BaseModel):
    """OA 单据：一次发起一行；flow_instance_id 关联 approval_instance（直通为 NULL）。"""

    __tablename__ = "oa_instance"

    display_no: Mapped[str] = mapped_column(String(32), index=True, comment="OA 编号（biz_type=oa 发号）")
    form_id: Mapped[int] = mapped_column(BigInteger, index=True)
    form_key: Mapped[str] = mapped_column(String(64), default="")
    form_name: Mapped[str] = mapped_column(String(128), default="")
    form_version: Mapped[int] = mapped_column(Integer, default=1)
    category: Mapped[str] = mapped_column(String(32), default="", index=True)
    schema_json: Mapped[str] = mapped_column(Text, nullable=True, comment="提交时表单结构快照")
    applicant_id: Mapped[int] = mapped_column(BigInteger, index=True)
    applicant_name: Mapped[str] = mapped_column(String(64), default="")
    form_data: Mapped[str] = mapped_column(Text, nullable=True, comment="表单数据 JSON")
    flow_instance_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="running", index=True, comment="running/approved/rejected/withdrawn/terminated"
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
