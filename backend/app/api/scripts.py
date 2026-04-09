"""
剧本管理路由

端点：
  POST   /generate/{project_id}        — 从 Brief 生成剧本（新版本）
  POST   /generate/{project_id}/stream  — [SSE] 流式生成剧本（打字机效果）
  GET    /{project_id}                  — 列出项目所有版本
  GET    /{project_id}/latest           — 获取最新版本
  PATCH  /{script_id}                   — 更新剧本内容（手动编辑）
  POST   /{script_id}/rewrite-section   — [旧] 重写自由文本段落（兼容保留）
  POST   /{script_id}/rewrite           — [新] 段落重写（按 index + 指令）
  POST   /{script_id}/rewrite/apply     — [新] 将预览的改写写入 DB
  POST   /{script_id}/rewrite/stream    — [SSE] 流式段落改写（打字机效果）
"""
import json
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
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
    generate_script_stream,
    rewrite_section,
    rewrite_paragraph,
    rewrite_paragraph_stream,
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


# ── SSE: 流式生成剧本 ─────────────────────────────────────────────────────────

@router.post("/generate/{project_id}/stream")
async def generate_script_stream_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    流式生成剧本 (SSE)。

    协议：
    - 每行格式：`data: <token>\n\n`
    - token 为 JSON 字符串的逐字符/词片段
    - 最终行：`data: [DONE]\n\n`（前端据此解析完整 JSON 并保存）
    - 错误行：`event: error\ndata: <message>\n\n`

    前端须将所有 token 拼接 → 在 [DONE] 收到后调用
    `POST /api/scripts/generate/{project_id}/save` 将完整 JSON 存库。
    """
    await get_project_for_user(project_id, db, user)
    guide = await get_guide_session_for_project(project_id, db, user)
    if not guide.completed:
        raise HTTPException(status_code=400, detail="Complete the guide session first")

    brief = guide.brief

    async def event_generator():
        try:
            async for token in generate_script_stream(brief):
                # SSE format: escape newlines inside token
                safe = token.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"event: error\ndata: {str(e)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx buffering
        },
    )


@router.post("/generate/{project_id}/save", response_model=ScriptOut)
async def save_streamed_script(
    project_id: str,
    payload: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    将 SSE 流式生成结束后前端拼接的完整 JSON 保存到 DB。
    payload: { "content": { ...script JSON... } }
    """
    await get_project_for_user(project_id, db, user)
    content = payload.get("content")
    if not content or not isinstance(content, dict):
        raise HTTPException(status_code=400, detail="content must be a JSON object")

    # 确认 guide 已完成（防止跳过流程直接调 save）
    guide = await get_guide_session_for_project(project_id, db, user)
    if not guide.completed:
        raise HTTPException(status_code=400, detail="Complete the guide session first")

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


# ── SSE: 流式段落改写 ──────────────────────────────────────────────────────────

@router.post("/{script_id}/rewrite/stream")
async def rewrite_paragraph_stream_endpoint(
    script_id: str,
    data: ParagraphRewriteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    流式段落改写 (SSE)。

    协议：
    - 每行格式：`data: <token>\n\n`
    - 最终行：`data: [DONE]\n\n`
    - 错误行：`event: error\ndata: <message>\n\n`

    前端须将所有 token 拼接 → 得到完整改写文本；
    然后调用 `POST /{script_id}/rewrite/apply` 保存到 DB。
    """
    script = await get_script_for_user(script_id, db, user)
    content = script.content
    paragraph_index = data.paragraph_index

    # 提前校验索引，在流开始前就能返回 400
    sections = (content or {}).get("sections", [])
    if paragraph_index < 0 or paragraph_index >= len(sections):
        raise HTTPException(
            status_code=400,
            detail=f"paragraph_index {paragraph_index} out of range (sections count: {len(sections)})",
        )

    async def event_generator():
        try:
            async for token in rewrite_paragraph_stream(content, paragraph_index, data.instruction):
                safe = token.replace("\n", "\\n")
                yield f"data: {safe}\n\n"
            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"event: error\ndata: {str(e)}\n\n"
        except Exception as e:
            yield f"event: error\ndata: LLM error: {str(e)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
