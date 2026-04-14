import asyncio
import json

import redis.asyncio as aioredis
from fastapi import APIRouter, status, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.clip_job import ClipJob
from app.models.project import Project
from app.models.user import User
from app.utils.jwt_utils import decode_token, get_bearer_token_from_header

router = APIRouter(tags=["websocket"])

# WebSocket 最长等待时间（秒），防止无限挂起
WS_TIMEOUT_SECONDS = 600  # 10 分钟
# DB 轮询间隔（秒），用于检测 cancelled/failed 状态
DB_POLL_INTERVAL = 3


async def _get_current_user_for_websocket(websocket: WebSocket) -> User | None:
    token = websocket.query_params.get("token")
    if not token:
        token = get_bearer_token_from_header(websocket.headers.get("authorization"))
    if not token:
        return None

    payload = decode_token(token)
    if not payload:
        return None

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.id == payload["sub"]))
        return result.scalar_one_or_none()


async def _user_can_access_clip_job(user_id: str, job_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(ClipJob.id)
            .join(Project, Project.id == ClipJob.project_id)
            .where(ClipJob.id == job_id, Project.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None


async def _get_job_status(job_id: str) -> dict | None:
    """从 DB 获取任务当前状态，用于轮询兜底。"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ClipJob).where(ClipJob.id == job_id))
        job = result.scalar_one_or_none()
        if not job:
            return None
        return {"status": job.status, "progress": job.progress, "error_msg": job.error_msg}


@router.websocket("/ws/clip/{job_id}")
async def clip_progress_ws(websocket: WebSocket, job_id: str):
    user = await _get_current_user_for_websocket(websocket)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    if not await _user_can_access_clip_job(user.id, job_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Forbidden")
        return

    await websocket.accept()

    # 连接前先检查任务是否已经结束（刷新页面重连时直接返回终态）
    initial = await _get_job_status(job_id)
    if initial and initial["status"] in ("done", "failed", "cancelled"):
        terminal_type = {
            "done": "done",
            "failed": "error",
            "cancelled": "cancelled",
        }[initial["status"]]
        await websocket.send_json({
            "type": terminal_type,
            "progress": initial["progress"],
            "message": initial["error_msg"] or initial["status"],
        })
        await websocket.close()
        return

    redis = aioredis.from_url(settings.REDIS_URL)
    pubsub = redis.pubsub()
    channel = f"clip:progress:{job_id}"
    await pubsub.subscribe(channel)

    done = asyncio.Event()

    async def _listen_pubsub():
        """订阅 Redis 推送，收到终态消息后设置 done。"""
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    payload = json.loads(data)
                    try:
                        await websocket.send_json(payload)
                    except Exception:
                        break
                    if payload.get("type") in ("done", "error") or payload.get("progress") in (100, -1):
                        done.set()
                        break
        except Exception:
            pass
        finally:
            done.set()

    async def _poll_db():
        """
        每隔 DB_POLL_INTERVAL 秒查一次 DB，
        处理 cancelled/Celery 崩溃等 pubsub 不会推送的终态。
        """
        elapsed = 0
        while not done.is_set():
            await asyncio.sleep(DB_POLL_INTERVAL)
            elapsed += DB_POLL_INTERVAL

            job_info = await _get_job_status(job_id)
            if not job_info:
                break

            if job_info["status"] == "cancelled":
                try:
                    await websocket.send_json({
                        "type": "cancelled",
                        "progress": job_info["progress"],
                        "message": "任务已被取消",
                    })
                except Exception:
                    pass
                done.set()
                break

            if job_info["status"] == "failed":
                try:
                    await websocket.send_json({
                        "type": "error",
                        "progress": job_info["progress"],
                        "message": job_info["error_msg"] or "任务失败",
                    })
                except Exception:
                    pass
                done.set()
                break

            if elapsed >= WS_TIMEOUT_SECONDS:
                try:
                    await websocket.send_json({
                        "type": "error",
                        "progress": job_info["progress"],
                        "message": f"任务超时（>{WS_TIMEOUT_SECONDS}s），请检查 Celery worker 是否正常运行，然后点击重试。",
                    })
                except Exception:
                    pass
                done.set()
                break

    try:
        listen_task = asyncio.create_task(_listen_pubsub())
        poll_task = asyncio.create_task(_poll_db())

        await done.wait()

        listen_task.cancel()
        poll_task.cancel()
        await asyncio.gather(listen_task, poll_task, return_exceptions=True)

    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.aclose()
