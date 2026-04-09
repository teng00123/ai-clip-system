from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
import uuid
from app.database import get_db
from app.models.project import Project
from app.models.user import User
from app.models.guide_session import GuideSession
from app.models.script import Script
from app.models.video import Video
from app.models.clip_job import ClipJob
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectOut
from app.utils.deps import get_current_user
from app.utils.storage import remove_object

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectOut)
async def create_project(data: ProjectCreate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    project = Project(id=str(uuid.uuid4()), user_id=user.id, name=data.name, description=data.description)
    db.add(project)
    await db.flush()
    return ProjectOut.model_validate(project)


@router.get("", response_model=List[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Project).where(Project.user_id == user.id).order_by(Project.created_at.desc()))
    return [ProjectOut.model_validate(p) for p in result.scalars().all()]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: str, data: ProjectUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    await db.flush()
    return ProjectOut.model_validate(project)


@router.delete("/{project_id}")
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    video_result = await db.execute(select(Video).where(Video.project_id == project_id))
    videos = video_result.scalars().all()
    clip_job_result = await db.execute(select(ClipJob).where(ClipJob.project_id == project_id))
    clip_jobs = clip_job_result.scalars().all()

    for video in videos:
        if video.storage_path:
            remove_object(video.storage_path)
    for job in clip_jobs:
        if job.output_path:
            remove_object(job.output_path)

    await db.execute(delete(ClipJob).where(ClipJob.project_id == project_id))
    await db.execute(delete(Video).where(Video.project_id == project_id))
    await db.execute(delete(Script).where(Script.project_id == project_id))
    await db.execute(delete(GuideSession).where(GuideSession.project_id == project_id))
    await db.delete(project)
    return {"ok": True}
