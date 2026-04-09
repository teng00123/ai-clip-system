from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.clip_job import ClipJob
from app.schemas.clip_job import ClipJobCreate, ClipJobOut
from app.services.clip_service import create_clip_job
from app.utils.deps import (
    get_current_user,
    get_project_for_user,
    get_video_for_user,
    get_clip_job_for_user,
    get_guide_session_for_project,
)
from app.utils.storage import get_presigned_url

router = APIRouter(prefix="/clips", tags=["clips"])


@router.post("", response_model=ClipJobOut)
async def submit_clip_job(data: ClipJobCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    project = await get_project_for_user(data.project_id, db, user)
    guide_session = await get_guide_session_for_project(data.project_id, db, user)
    if not guide_session.completed:
        raise HTTPException(status_code=400, detail="Complete the guide session before starting clip generation")

    await get_video_for_user(data.video_id, db, user, project_id=data.project_id)
    job = await create_clip_job(db, data.project_id, data.video_id)

    if project.status in {"draft", "scripting"}:
        project.status = "clipping"
        await db.flush()

    return ClipJobOut.model_validate(job)


@router.get("/{job_id}", response_model=ClipJobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    job = await get_clip_job_for_user(job_id, db, user)
    return ClipJobOut.model_validate(job)


@router.get("/project/{project_id}", response_model=List[ClipJobOut])
async def list_project_jobs(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await get_project_for_user(project_id, db, user)
    result = await db.execute(
        select(ClipJob).where(ClipJob.project_id == project_id).order_by(ClipJob.created_at.desc())
    )
    return [ClipJobOut.model_validate(j) for j in result.scalars().all()]


@router.get("/{job_id}/download-url")
async def get_download_url(job_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    job = await get_clip_job_for_user(job_id, db, user)
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=400, detail="Output not ready")
    url = get_presigned_url(job.output_path, expires_hours=2)
    return {"url": url, "expires_in": "2h"}
