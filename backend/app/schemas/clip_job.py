from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel


class ClipJobCreate(BaseModel):
    project_id: str
    video_id: str


class ClipJobOut(BaseModel):
    id: str
    project_id: str
    video_id: str
    status: str
    clip_plan: Optional[Dict]
    progress: int
    output_path: Optional[str]
    error_msg: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
