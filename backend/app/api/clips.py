from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.clip_job import ClipJob
from app.schemas.clip_job import ClipJobCreate, ClipJobOut, ClipPlanPatch
from app.services.clip_service import create_clip_job
from app.utils.deps import (
    get_current_user,
    get_project_for_user,
    get_video_for_user,
    get_clip_job_for_user,
    get_guide_session_for_project,
)
from app.utils.storage import get_presigned_url
from app.tasks.clip_task import rerender_clip_job, process_clip_job
from app.tasks.celery_app import celery_app
import logging

logger = logging.getLogger(__name__)
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


@router.get("/project/{project_id}", response_model=List[ClipJobOut])
async def list_project_jobs(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await get_project_for_user(project_id, db, user)
    result = await db.execute(
        select(ClipJob).where(ClipJob.project_id == project_id).order_by(ClipJob.created_at.desc())
    )
    return [ClipJobOut.model_validate(j) for j in result.scalars().all()]


@router.get("/{job_id}", response_model=ClipJobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    job = await get_clip_job_for_user(job_id, db, user)
    return ClipJobOut.model_validate(job)


@router.patch("/{job_id}/plan", response_model=ClipJobOut)
async def patch_clip_plan(
    job_id: str,
    patch: ClipPlanPatch,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    更新剪辑方案。只允许在任务完成后操作。

    支持：
    - 调整片段的 start/end（剪切）
    - 删除片段（不传该 id）
    - 修改字幕文本
    - 重新排序（按数组顺序）
    """
    job = await get_clip_job_for_user(job_id, db, user)
    if job.status not in ("done", "failed"):
        raise HTTPException(
            status_code=400,
            detail="Can only patch plan on completed/failed jobs",
        )

    # Build updated plan
    old_plan = job.clip_plan or {}
    new_segments = [
        {
            "id": seg.id,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "duration": round(seg.end - seg.start, 3),
            "transcript": seg.transcript if seg.transcript is not None else (
                next(
                    (s.get("transcript", "") for s in old_plan.get("segments", []) if s["id"] == seg.id),
                    "",
                )
            ),
        }
        for seg in patch.segments
    ]

    new_plan = {
        "segments": new_segments,
        "total_scenes": len(new_segments),
        "total_duration": round(sum(s["duration"] for s in new_segments), 3),
    }

    await db.execute(
        update(ClipJob)
        .where(ClipJob.id == job_id)
        .values(clip_plan=new_plan)
    )
    await db.flush()

    # Reload
    result = await db.execute(select(ClipJob).where(ClipJob.id == job_id))
    updated_job = result.scalars().first()
    return ClipJobOut.model_validate(updated_job)


@router.get("/{job_id}/download-url")
async def get_download_url(job_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    job = await get_clip_job_for_user(job_id, db, user)
    if job.status != "done" or not job.output_path:
        raise HTTPException(status_code=400, detail="Output not ready")
    url = get_presigned_url(job.output_path, expires_hours=2)
    return {"url": url, "expires_in": "2h"}


@router.post("/{job_id}/rerender", response_model=ClipJobOut)
async def rerender_clip_job_endpoint(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    用当前 clip_plan 重新渲染视频。
    要求 job 处于 done/failed 状态，且 clip_plan 已存在。
    """
    job = await get_clip_job_for_user(job_id, db, user)

    if job.status not in ("done", "failed"):
        raise HTTPException(
            status_code=400,
            detail="Can only rerender a completed/failed job",
        )

    plan = job.clip_plan
    if not plan or not plan.get("segments"):
        raise HTTPException(
            status_code=400,
            detail="clip_plan is empty — cannot rerender without segments",
        )

    if not job.video_id:
        raise HTTPException(status_code=400, detail="No video associated with this job")

    # Reset to pending before dispatching
    await db.execute(
        update(ClipJob)
        .where(ClipJob.id == job_id)
        .values(status="pending", progress=0, error_msg=None)
    )
    await db.flush()

    # Dispatch Celery rerender task
    r = rerender_clip_job.delay(job_id, job.video_id)
    await db.execute(
        update(ClipJob).where(ClipJob.id == job_id).values(celery_task_id=r.id)
    )
    await db.flush()

    # Return updated job
    result = await db.execute(select(ClipJob).where(ClipJob.id == job_id))
    updated = result.scalars().first()
    return ClipJobOut.model_validate(updated)


@router.post("/{job_id}/cancel", response_model=ClipJobOut)
async def cancel_clip_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    终止进行中的剪辑任务。
    - 如果 Celery 任务还在运行，发送 revoke 并尝试中断
    - 无论是否 revoke 成功，都把 DB 状态改为 cancelled
    """
    job = await get_clip_job_for_user(job_id, db, user)

    if job.status not in ("pending", "processing"):
        raise HTTPException(
            status_code=400,
            detail=f"任务状态为 {job.status!r}，只有 pending/processing 状态的任务可以终止",
        )

    # 尝试 revoke Celery 任务
    if job.celery_task_id:
        try:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
            logger.info("Revoked Celery task %s for job %s", job.celery_task_id, job_id)
        except Exception as exc:
            logger.warning("Failed to revoke Celery task %s: %s", job.celery_task_id, exc)

    await db.execute(
        update(ClipJob)
        .where(ClipJob.id == job_id)
        .values(status="cancelled", error_msg="用户手动终止")
    )
    await db.flush()

    result = await db.execute(select(ClipJob).where(ClipJob.id == job_id))
    return ClipJobOut.model_validate(result.scalars().first())


@router.post("/{job_id}/retry", response_model=ClipJobOut)
async def retry_clip_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    重试失败、超时或被取消的剪辑任务。
    重新发起完整的 process_clip_job 流程（重新分析+渲染）。
    """
    job = await get_clip_job_for_user(job_id, db, user)

    if job.status not in ("failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"任务状态为 {job.status!r}，只有 failed/cancelled 状态可以重试",
        )

    if not job.video_id:
        raise HTTPException(status_code=400, detail="该任务没有关联视频，无法重试")

    # 重置状态
    await db.execute(
        update(ClipJob)
        .where(ClipJob.id == job_id)
        .values(status="pending", progress=0, error_msg=None, celery_task_id=None)
    )
    await db.flush()

    # 重新发送完整流程
    try:
        r = process_clip_job.delay(job_id, job.video_id)
        await db.execute(
            update(ClipJob).where(ClipJob.id == job_id).values(celery_task_id=r.id)
        )
        await db.flush()
        logger.info("Retried clip job %s, new task_id=%s", job_id, r.id)
    except Exception as exc:
        await db.execute(
            update(ClipJob).where(ClipJob.id == job_id)
            .values(status="failed", error_msg=f"重试失败: {exc}")
        )
        await db.flush()
        raise HTTPException(status_code=503, detail=f"任务队列不可用，重试失败: {exc}")

    result = await db.execute(select(ClipJob).where(ClipJob.id == job_id))
    return ClipJobOut.model_validate(result.scalars().first())
