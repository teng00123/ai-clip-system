from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel


class VideoOut(BaseModel):
    id: str
    project_id: str
    filename: str
    source: str
    storage_path: Optional[str]
    duration: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True
