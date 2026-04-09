import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.types import JsonType


class Script(Base):
    __tablename__ = "scripts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    format: Mapped[str] = mapped_column(String(50), default="voiceover")
    content: Mapped[dict] = mapped_column(JsonType, nullable=False)
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
