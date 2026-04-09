import os
import shutil
import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video import Video
from app.utils.storage import upload_file

UPLOAD_TMP_DIR = "/tmp/ai-clip-uploads"
os.makedirs(UPLOAD_TMP_DIR, exist_ok=True)


async def save_uploaded_video(
    db: AsyncSession,
    project_id: str,
    file: UploadFile,
    max_file_size: int,
) -> Video:
    video_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1] or ".mp4"
    tmp_path = os.path.join(UPLOAD_TMP_DIR, f"{video_id}{ext}")
    object_name = f"videos/{project_id}/{video_id}{ext}"

    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        file_size = os.path.getsize(tmp_path)
        if file_size > max_file_size:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 500MB")

        duration = _get_duration(tmp_path)
        upload_file(object_name, tmp_path, content_type=file.content_type or "video/mp4")

        video = Video(
            id=video_id,
            project_id=project_id,
            filename=file.filename,
            source="local",
            storage_path=object_name,
            duration=duration,
            file_size=str(file_size),
        )
        db.add(video)
        await db.flush()
        return video
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _get_duration(path: str) -> Optional[float]:
    try:
        import ffmpeg
        probe = ffmpeg.probe(path)
        duration = float(probe["format"]["duration"])
        return duration
    except Exception:
        return None
