from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.clip_job import ClipJob
from app.models.guide_session import GuideSession
from app.models.project import Project
from app.models.script import Script
from app.models.user import User
from app.models.video import Video
from app.utils.jwt_utils import decode_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    result = await db.execute(select(User).where(User.id == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


async def get_project_for_user(project_id: str, db: AsyncSession, user: User) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id, Project.user_id == user.id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


async def get_guide_session_for_project(project_id: str, db: AsyncSession, user: User) -> GuideSession:
    await get_project_for_user(project_id, db, user)
    result = await db.execute(select(GuideSession).where(GuideSession.project_id == project_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guide session not started")
    return session


async def get_script_for_user(script_id: str, db: AsyncSession, user: User) -> Script:
    result = await db.execute(
        select(Script)
        .join(Project, Project.id == Script.project_id)
        .where(Script.id == script_id, Project.user_id == user.id)
    )
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return script


async def get_video_for_user(video_id: str, db: AsyncSession, user: User, project_id: str | None = None) -> Video:
    stmt = (
        select(Video)
        .join(Project, Project.id == Video.project_id)
        .where(Video.id == video_id, Project.user_id == user.id)
    )
    if project_id is not None:
        stmt = stmt.where(Video.project_id == project_id)
    result = await db.execute(stmt)
    video = result.scalar_one_or_none()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


async def get_clip_job_for_user(job_id: str, db: AsyncSession, user: User) -> ClipJob:
    result = await db.execute(
        select(ClipJob)
        .join(Project, Project.id == ClipJob.project_id)
        .where(ClipJob.id == job_id, Project.user_id == user.id)
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Clip job not found")
    return job
