import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clip_job import ClipJob
from app.tasks.clip_task import process_clip_job

ACTIVE_JOB_STATUSES = {"pending", "processing"}


async def create_clip_job(db: AsyncSession, project_id: str, video_id: str) -> ClipJob:
    existing = await db.execute(
        select(ClipJob).where(
            ClipJob.project_id == project_id,
            ClipJob.video_id == video_id,
            ClipJob.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    active_job = existing.scalar_one_or_none()
    if active_job:
        raise HTTPException(status_code=409, detail="A clip job is already running for this video")

    job = ClipJob(
        id=str(uuid.uuid4()),
        project_id=project_id,
        video_id=video_id,
        status="pending",
    )
    db.add(job)
    await db.flush()
    process_clip_job.delay(job.id, video_id)
    return job


async def get_clip_job(db: AsyncSession, job_id: str) -> ClipJob:
    result = await db.execute(select(ClipJob).where(ClipJob.id == job_id))
    return result.scalar_one_or_none()
