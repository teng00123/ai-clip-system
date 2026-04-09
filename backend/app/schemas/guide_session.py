from datetime import datetime
from typing import Optional, Any, Dict, List
from pydantic import BaseModel


class AnswerSubmit(BaseModel):
    step: int
    answer: Any


class QuestionOut(BaseModel):
    step: int
    total_steps: int
    question_text: str
    question_type: str
    options: Optional[List[str]] = None


class GuideSessionOut(BaseModel):
    id: str
    project_id: str
    answers: Dict
    brief: Optional[Dict]
    step: int
    completed: bool

    class Config:
        from_attributes = True
