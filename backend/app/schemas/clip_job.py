from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


class ClipJobCreate(BaseModel):
    project_id: str
    video_id: str


class SegmentPatch(BaseModel):
    """Single segment update in a plan patch"""
    id: int
    start: float = Field(..., ge=0)
    end: float = Field(..., ge=0)
    transcript: Optional[str] = None

    def validate_times(self):
        if self.end <= self.start:
            raise ValueError(f"Segment {self.id}: end must be > start")


class ClipPlanPatch(BaseModel):
    """
    Payload for PATCH /clips/{job_id}/plan.
    Allows reordering, trimming, or deleting segments.
    `segments` is the full updated list (replaces existing).
    """
    segments: List[SegmentPatch]

    def model_post_init(self, __context):
        for seg in self.segments:
            seg.validate_times()


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
