import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.types import JsonType


def _utcnow() -> datetime:
    """Python 层生成 UTC 时间，避免 server_default 导致 async lazy load 问题。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    format: Mapped[str] = mapped_column(String(50), default="voiceover")
    content: Mapped[dict] = mapped_column(JsonType, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
