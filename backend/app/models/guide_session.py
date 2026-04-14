import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.types import JsonType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GuideSession(Base):
    __tablename__ = "guide_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    answers: Mapped[dict] = mapped_column(JsonType, default=dict)
    brief: Mapped[dict] = mapped_column(JsonType, nullable=True)
    step: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    # 动态问答模式：存储完整对话历史 [{role: str, content: str}]
    conversation_history: Mapped[list] = mapped_column(JsonType, default=list, nullable=True)
    # 问答模式标记
    mode: Mapped[str] = mapped_column(String(20), default="static", nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
