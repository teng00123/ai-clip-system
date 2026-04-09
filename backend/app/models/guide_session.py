import uuid
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, Boolean, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base
from app.models.types import JsonType


class GuideSession(Base):
    __tablename__ = "guide_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String, ForeignKey("projects.id"), nullable=False)
    answers: Mapped[dict] = mapped_column(JsonType, default=dict)
    brief: Mapped[dict] = mapped_column(JsonType, nullable=True)
    step: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
