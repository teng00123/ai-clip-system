from datetime import datetime
from typing import Optional, Dict, List
from pydantic import BaseModel, Field


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


class ParagraphRewriteRequest(BaseModel):
    paragraph_index: int = Field(..., ge=0, description="要改写的段落索引（sections 数组下标）")
    instruction: str = Field(..., min_length=2, max_length=500, description="改写指令，如：更幽默、更简短、加入数据")
    preview: bool = Field(True, description="True=仅返回预览，不修改数据库；False=直接应用")


class ParagraphRewriteOut(BaseModel):
    script_id: str
    paragraph_index: int
    section_title: str
    original: str
    rewritten: str
    instruction: str
    applied: bool = False  # True 表示已直接写入 DB


class ApplyRewriteRequest(BaseModel):
    paragraph_index: int = Field(..., ge=0)
    rewritten_text: str = Field(..., min_length=1, description="要应用的改写文本")
