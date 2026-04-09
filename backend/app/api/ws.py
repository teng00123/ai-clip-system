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
    redis = aioredis.from_url(settings.REDIS_URL)
    pubsub = redis.pubsub()
    channel = f"clip:progress:{job_id}"
    await pubsub.subscribe(channel)

    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                payload = json.loads(data)
                await websocket.send_json(payload)
                if payload.get("progress") in (100, -1):
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
        await redis.aclose()
