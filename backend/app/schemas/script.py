from datetime import datetime
from typing import Optional, Dict
from pydantic import BaseModel


class ScriptCreate(BaseModel):
    project_id: str
    format: str = "voiceover"
    content: Dict


class ScriptUpdate(BaseModel):
    content: Dict


class ScriptOut(BaseModel):
    id: str
    project_id: str
    version: int
    format: str
    content: Dict
    is_latest: bool
    created_at: datetime

    class Config:
        from_attributes = True
