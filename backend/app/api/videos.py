from fastapi import APIRouter, Depends, Request, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List
from app.database import get_db
from app.models.user import User
from app.models.video import Video
from app.schemas.video import VideoOut
from app.services.video_service import save_uploaded_video
from app.utils.deps import get_current_user, get_project_for_user, get_video_for_user
from app.utils.storage import get_presigned_url

router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_CONTENT_TYPES = {"video/mp4", "video/quicktime", "video/x-msvideo", "video/avi"}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB


@router.post("/{project_id}/upload", response_model=VideoOut)
async def upload_video(
    project_id: str,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Check content-length header first (fast path, before reading body)
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > MAX_FILE_SIZE:
                raise HTTPException(status_code=400, detail="File too large. Maximum size is 500MB")
        except ValueError:
            pass

    await get_project_for_user(project_id, db, user)
    if file.content_type and file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    video = await save_uploaded_video(db, project_id, file, max_file_size=MAX_FILE_SIZE)
    return VideoOut.model_validate(video)


@router.get("/{project_id}", response_model=List[VideoOut])
async def list_videos(project_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await get_project_for_user(project_id, db, user)
    result = await db.execute(select(Video).where(Video.project_id == project_id))
    return [VideoOut.model_validate(v) for v in result.scalars().all()]


@router.get("/{project_id}/{video_id}/url")
async def get_video_url(project_id: str, video_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    await get_project_for_user(project_id, db, user)
    video = await get_video_for_user(video_id, db, user, project_id=project_id)
    url = get_presigned_url(video.storage_path)
    return {"url": url, "expires_in": "24h"}
