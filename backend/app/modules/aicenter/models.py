"""AI 中心：ai_usage_log（全站 AI 调用用量日志，网关统一落行）+ ai_knowledge（知识库条目）。"""

from sqlalchemy import BigInteger, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.common.models import BaseModel


class AiUsageLog(BaseModel):
    """一次 AI 网关调用一行：成功/失败/回退都记录（token 统计只计 success）。"""

    __tablename__ = "ai_usage_log"
    __table_args__ = (
        Index("ix_ai_usage_feature_time", "feature", "create_time"),
        Index("ix_ai_usage_user_time", "user_id", "create_time"),
    )

    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="调用用户")
    user_name: Mapped[str] = mapped_column(String(64), default="")
    feature: Mapped[str] = mapped_column(
        String(32), index=True, comment="功能：quote/contract_ocr/task_photo/report_summary"
    )
    model: Mapped[str] = mapped_column(String(64), default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, comment="端到端耗时（含重试）")
    status: Mapped[str] = mapped_column(String(16), index=True, comment="success/error/fallback")
    error: Mapped[str] = mapped_column(String(500), default="", comment="失败/回退原因")
    biz_type: Mapped[str] = mapped_column(String(32), default="", comment="关联业务类型")
    biz_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, comment="关联业务 id")
    prompt_version: Mapped[str] = mapped_column(String(16), default="")


class KnowledgeEntry(BaseModel):
    """AI 知识库条目：标题/分类/正文 + 可选附件；供全局助手与知识库问答检索。"""

    __tablename__ = "ai_knowledge"
    __table_args__ = (Index("ix_ai_knowledge_category", "category"),)

    title: Mapped[str] = mapped_column(String(128), comment="条目标题")
    category: Mapped[str] = mapped_column(String(64), default="", comment="分类（自由文本）")
    content: Mapped[str] = mapped_column(Text, default="", comment="正文")
    attachment_path: Mapped[str] = mapped_column(String(255), default="", comment="附件相对路径（空=无）")
    attachment_name: Mapped[str] = mapped_column(String(255), default="", comment="附件原始文件名")
