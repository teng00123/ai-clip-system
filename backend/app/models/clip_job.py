import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.types import JsonType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ClipJob(Base):
    __tablename__ = "clip_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    video_id: Mapped[str] = mapped_column(String(36), ForeignKey("videos.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    clip_plan: Mapped[dict] = mapped_column(JsonType, nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    output_path: Mapped[str] = mapped_column(String(500), nullable=True)
    error_msg: Mapped[str] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
