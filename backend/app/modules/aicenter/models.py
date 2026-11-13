"""AI 中心：ai_usage_log（全站 AI 调用用量日志，网关统一落行）。"""

from sqlalchemy import BigInteger, Index, Integer, String
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
