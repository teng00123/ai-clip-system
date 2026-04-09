from celery import Celery
from app.config import settings

celery_app = Celery(
    "ai_clip",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.tasks.clip_task"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
)
