from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
import uuid
from app.database import get_db
from app.models.user import User
from app.models.script import Script
from app.schemas.script import ScriptUpdate, ScriptOut
from app.services.script_service import generate_script, rewrite_section
from app.utils.deps import get_current_user, get_project_for_user, get_guide_session_for_project, get_script_for_user

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
async def list_scripts(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await get_project_for_user(project_id, db, user)
    result = await db.execute(
        select(Script).where(Script.project_id == project_id).order_by(Script.version.desc())
    )
    return [ScriptOut.model_validate(s) for s in result.scalars().all()]


@router.get("/{project_id}/latest", response_model=ScriptOut)
async def get_latest_script(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await get_project_for_user(project_id, db, user)
    result = await db.execute(
        select(Script).where(Script.project_id == project_id, Script.is_latest == True)
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="No script found")
    return ScriptOut.model_validate(script)


@router.patch("/{script_id}", response_model=ScriptOut)
async def update_script(script_id: str, data: ScriptUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    script = await get_script_for_user(script_id, db, user)
    script.content = data.content
    await db.flush()
    return ScriptOut.model_validate(script)


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
