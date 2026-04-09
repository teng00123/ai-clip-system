"""
剧本管理路由

端点：
  POST   /generate/{project_id}        — 从 Brief 生成剧本（新版本）
  GET    /{project_id}                  — 列出项目所有版本
  GET    /{project_id}/latest           — 获取最新版本
  PATCH  /{script_id}                   — 更新剧本内容（手动编辑）
  POST   /{script_id}/rewrite-section   — [旧] 重写自由文本段落（兼容保留）
  POST   /{script_id}/rewrite           — [新] 段落重写（按 index + 指令）
  POST   /{script_id}/rewrite/apply     — [新] 将预览的改写写入 DB
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
import uuid
from app.database import get_db
from app.models.user import User
from app.models.script import Script
from app.schemas.script import (
    ScriptUpdate,
    ScriptOut,
    ParagraphRewriteRequest,
    ParagraphRewriteOut,
    ApplyRewriteRequest,
)
from app.services.script_service import (
    generate_script,
    rewrite_section,
    rewrite_paragraph,
    apply_rewrite,
)
from app.utils.deps import (
    get_current_user,
    get_project_for_user,
    get_guide_session_for_project,
    get_script_for_user,
)

router = APIRouter(prefix="/scripts", tags=["scripts"])


@router.post("/generate/{project_id}", response_model=ScriptOut)
async def generate_script_for_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await get_project_for_user(project_id, db, user)
    guide = await get_guide_session_for_project(project_id, db, user)
    if not guide.completed:
        raise HTTPException(status_code=400, detail="Complete the guide session first")

    content = await generate_script(guide.brief)

    await db.execute(
        update(Script).where(Script.project_id == project_id).values(is_latest=False)
    )

    result2 = await db.execute(
        select(Script).where(Script.project_id == project_id).order_by(Script.version.desc())
    )
    latest = result2.scalars().first()
    version = (latest.version + 1) if latest else 1

    script = Script(
        id=str(uuid.uuid4()),
        project_id=project_id,
        version=version,
        format="voiceover",
        content=content,
        is_latest=True,
    )
    db.add(script)

    project = await get_project_for_user(project_id, db, user)
    if project.status in {"draft", "scripting"}:
        project.status = "scripting"

    await db.flush()
    return ScriptOut.model_validate(script)


@router.get("/{project_id}", response_model=List[ScriptOut])
async def list_scripts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await get_project_for_user(project_id, db, user)
    result = await db.execute(
        select(Script).where(Script.project_id == project_id).order_by(Script.version.desc())
    )
    return [ScriptOut.model_validate(s) for s in result.scalars().all()]


@router.get("/{project_id}/latest", response_model=ScriptOut)
async def get_latest_script(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await get_project_for_user(project_id, db, user)
    result = await db.execute(
        select(Script).where(Script.project_id == project_id, Script.is_latest == True)
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="No script found")
    return ScriptOut.model_validate(script)


@router.patch("/{script_id}", response_model=ScriptOut)
async def update_script(
    script_id: str,
    data: ScriptUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    script = await get_script_for_user(script_id, db, user)
    script.content = data.content
    await db.flush()
    return ScriptOut.model_validate(script)


# ── [旧] 自由文本段落重写（保持兼容） ──────────────────────────────────────────

@router.post("/{script_id}/rewrite-section")
async def rewrite_script_section(
    script_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await get_script_for_user(script_id, db, user)
    section_content = payload.get("section_content", "")
    instruction = payload.get("instruction", "")
    new_text = await rewrite_section(section_content, instruction)
    return {"rewritten": new_text}


# ── [新] 段落重写（按 index） ────────────────────────────────────────────────

@router.post("/{script_id}/rewrite", response_model=ParagraphRewriteOut)
async def rewrite_paragraph_endpoint(
    script_id: str,
    data: ParagraphRewriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    对指定段落（sections[paragraph_index]）进行 LLM 改写。

    - `preview=true`（默认）：仅返回改写结果，不修改 DB
    - `preview=false`：改写后直接保存到 DB
    """
    script = await get_script_for_user(script_id, db, user)

    try:
        result = await rewrite_paragraph(
            script_content=script.content,
            paragraph_index=data.paragraph_index,
            instruction=data.instruction,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"LLM error: {str(e)}")

    applied = False
    if not data.preview:
        # 直接写入 DB
        new_content = apply_rewrite(script.content, data.paragraph_index, result["rewritten"])
        script.content = new_content
        await db.flush()
        applied = True

    return ParagraphRewriteOut(
        script_id=script_id,
        paragraph_index=result["paragraph_index"],
        section_title=result["section_title"],
        original=result["original"],
        rewritten=result["rewritten"],
        instruction=result["instruction"],
        applied=applied,
    )


@router.post("/{script_id}/rewrite/apply", response_model=ScriptOut)
async def apply_rewrite_endpoint(
    script_id: str,
    data: ApplyRewriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    将预览模式（preview=true）生成的改写文本应用到 DB。
    用于「先预览 → 用户确认 → 再保存」的两步流程。
    """
    script = await get_script_for_user(script_id, db, user)

    sections = (script.content or {}).get("sections", [])
    if data.paragraph_index < 0 or data.paragraph_index >= len(sections):
        raise HTTPException(
            status_code=400,
            detail=f"paragraph_index {data.paragraph_index} out of range",
        )

    new_content = apply_rewrite(script.content, data.paragraph_index, data.rewritten_text)
    script.content = new_content
    await db.flush()

    return ScriptOut.model_validate(script)
