import uuid
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clip_job import ClipJob
from app.tasks.clip_task import process_clip_job

logger = logging.getLogger(__name__)

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

    try:
        result = process_clip_job.delay(job.id, video_id)
        job.celery_task_id = result.id
        logger.info("Clip job %s dispatched to Celery, task_id=%s", job.id, result.id)
    except Exception as exc:
        logger.error("Failed to dispatch clip job %s to Celery: %s", job.id, exc)
        job.status = "failed"
        job.error_msg = (
            f"无法发送任务到队列: {exc}。"
            "请检查 Redis 是否运行，以及 REDIS_URL 配置是否正确（裸机运行应为 redis://localhost:6379/0）。"
        )
        raise HTTPException(
            status_code=503,
            detail=f"任务队列不可用，请检查 Redis 连接。错误: {exc}",
        )

    return job


async def get_clip_job(db: AsyncSession, job_id: str) -> ClipJob:
    result = await db.execute(select(ClipJob).where(ClipJob.id == job_id))
    return result.scalar_one_or_none()
