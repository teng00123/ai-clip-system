import uuid
from datetime import datetime, timezone
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.types import JsonType


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="local")
    original_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=True)
    duration: Mapped[float] = mapped_column(Float, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JsonType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
