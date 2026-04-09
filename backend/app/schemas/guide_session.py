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
    is_dynamic: bool = False  # 标记是否为动态模式问题


class DynamicAnswerSubmit(BaseModel):
    """动态模式下的答案提交（无需 step 序号，由对话历史驱动）"""
    answer: str


class DynamicQuestionOut(BaseModel):
    """动态模式返回的问题"""
    question: str
    question_type: str  # single_choice | multi_choice | text_input
    options: Optional[List[str]] = None
    is_complete: bool = False
    answers_count: int = 0  # 已回答问题数
    mode: str = "dynamic"


class GuideSessionOut(BaseModel):
    id: str
    project_id: str
    answers: Dict
    brief: Optional[Dict]
    step: int
    completed: bool
    mode: str = "static"
    conversation_history: Optional[List[Dict]] = None

    class Config:
        from_attributes = True
