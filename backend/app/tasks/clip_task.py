"""
Celery task: process_clip_job
=================================
Full pipeline:
  1. Download video from MinIO to tmpdir
  2. Scene detection (PySceneDetect / ContentDetector)
  3. ASR subtitle generation (OpenAI Whisper API)
  4. Build clip_plan JSON
  5. Write SRT file
  6. FFmpeg render (concat + optional subtitle burn)
  7. Upload output MP4 to MinIO
  8. Update ClipJob in DB → done / failed

Progress broadcast via Redis pub/sub on channel  clip:progress:{job_id}
Message schema: {"type": "progress"|"done"|"error", "progress": 0-100, "message": "..."}
"""

import json
import logging
import os
import subprocess
import tempfile

import redis as redis_lib

from app.config import settings
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Redis helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_redis():
    return redis_lib.from_url(settings.REDIS_URL, socket_connect_timeout=5)


def _publish(job_id: str, msg_type: str, progress: int, message: str = ""):
    payload = json.dumps({"type": msg_type, "progress": progress, "message": message})
    try:
        _get_redis().publish(f"clip:progress:{job_id}", payload)
    except Exception as exc:
        logger.warning("Redis publish failed for job %s: %s", job_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# DB helpers  (sync, Celery worker context — no async)
# ─────────────────────────────────────────────────────────────────────────────

def _make_sync_engine():
    """
    Derive a sync SQLAlchemy engine from DATABASE_URL.
    Supports:
      postgresql+asyncpg://...  → psycopg2
      sqlite+aiosqlite://...    → sqlite
      postgresql://...          → psycopg2 (unchanged)
      sqlite:///...             → sqlite (unchanged)
    """
    from sqlalchemy import create_engine

    url = settings.DATABASE_URL
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    elif "+aiosqlite" in url:
        url = url.replace("+aiosqlite", "")
    return create_engine(url, pool_pre_ping=True)


def _fetch_video_storage_path(video_id: str) -> str:
    from sqlalchemy import text

    engine = _make_sync_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT storage_path FROM videos WHERE id=:vid"),
            {"vid": video_id},
        ).fetchone()
    engine.dispose()
    if not row:
        raise ValueError(f"Video {video_id!r} not found in database")
    return row[0]


def _update_job(
    job_id: str,
    *,
    status: str,
    progress: int,
    clip_plan: dict | None = None,
    output_path: str | None = None,
    error_msg: str | None = None,
):
    """Update ClipJob row using raw SQL to avoid async engine dependency."""
    from sqlalchemy import text

    engine = _make_sync_engine()
    set_clauses = ["status=:status", "progress=:progress", "updated_at=now()"]
    params: dict = {"job_id": job_id, "status": status, "progress": progress}

    if clip_plan is not None:
        set_clauses.append("clip_plan=:clip_plan")
        params["clip_plan"] = json.dumps(clip_plan)

    if output_path is not None:
        set_clauses.append("output_path=:output_path")
        params["output_path"] = output_path

    if error_msg is not None:
        set_clauses.append("error_msg=:error_msg")
        params["error_msg"] = error_msg[:1000]  # column limit

    sql = f"UPDATE clip_jobs SET {', '.join(set_clauses)} WHERE id=:job_id"
    with engine.connect() as conn:
        conn.execute(text(sql), params)
        conn.commit()
    engine.dispose()


# ─────────────────────────────────────────────────────────────────────────────
# Celery task
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="clip_task.process_clip_job",
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def process_clip_job(self, job_id: str, video_id: str):
    """
    Main Celery task. Orchestrates the full clip pipeline.
    All heavy work happens inside a TemporaryDirectory that is cleaned up
    automatically on success or failure.
    """
    logger.info("Starting clip job %s for video %s", job_id, video_id)

    try:
        # ── 1. Mark as processing ──────────────────────────────────────────
        _update_job(job_id, status="processing", progress=5)
        _publish(job_id, "progress", 5, "Initialising…")

        # ── 2. Fetch video path from DB ────────────────────────────────────
        storage_path = _fetch_video_storage_path(video_id)

        with tempfile.TemporaryDirectory(prefix="clip_") as tmpdir:
            local_video = os.path.join(tmpdir, "input.mp4")

            # ── 3. Download video from MinIO ───────────────────────────────
            _publish(job_id, "progress", 10, "Downloading video…")
            from app.utils.storage import download_file
            download_file(storage_path, local_video)
            logger.info("Video downloaded to %s (%d bytes)", local_video, os.path.getsize(local_video))

            # ── 4. Scene detection ─────────────────────────────────────────
            _publish(job_id, "progress", 20, "Detecting scenes…")
            scenes = _detect_scenes(local_video)
            logger.info("Detected %d scenes", len(scenes))
            _publish(job_id, "progress", 40, f"Detected {len(scenes)} scene(s)")

            # ── 5. ASR subtitle generation ─────────────────────────────────
            _publish(job_id, "progress", 45, "Transcribing audio (Whisper)…")
            subtitles = _generate_subtitles(local_video)
            logger.info("Whisper returned %d subtitle segments", len(subtitles))
            _publish(job_id, "progress", 65, f"Transcribed {len(subtitles)} segment(s)")

            # ── 6. Build clip plan ─────────────────────────────────────────
            clip_plan = _build_clip_plan(scenes, subtitles)
            _publish(job_id, "progress", 70, "Clip plan built")
            # Persist clip_plan early so frontend can show segments before render
            _update_job(job_id, status="processing", progress=70, clip_plan=clip_plan)

            # ── 7. Write SRT ───────────────────────────────────────────────
            srt_path = os.path.join(tmpdir, "subtitles.srt")
            has_subs = _write_srt(subtitles, srt_path)

            # ── 8. FFmpeg render ───────────────────────────────────────────
            _publish(job_id, "progress", 75, "Rendering video…")
            output_local = os.path.join(tmpdir, "output.mp4")
            _render_video(local_video, scenes, srt_path if has_subs else None, output_local)
            out_size = os.path.getsize(output_local) if os.path.exists(output_local) else 0
            logger.info("Render complete: %s (%d bytes)", output_local, out_size)

            # ── 9. Upload output ───────────────────────────────────────────
            _publish(job_id, "progress", 90, "Uploading result…")
            output_object = f"outputs/{job_id}/output.mp4"
            from app.utils.storage import upload_file
            upload_file(output_object, output_local, content_type="video/mp4")

        # ── 10. Mark done ──────────────────────────────────────────────────
        _update_job(
            job_id,
            status="done",
            progress=100,
            clip_plan=clip_plan,
            output_path=output_object,
        )
        _publish(job_id, "done", 100, "Finished! Your clip is ready.")
        logger.info("Clip job %s completed successfully", job_id)

    except Exception as exc:
        logger.exception("Clip job %s failed: %s", job_id, exc)
        _update_job(job_id, status="failed", progress=0, error_msg=str(exc))
        _publish(job_id, "error", -1, f"Failed: {exc}")
        raise  # let Celery handle retries / failure state


# ─────────────────────────────────────────────────────────────────────────────
# Step implementations
# ─────────────────────────────────────────────────────────────────────────────

def _detect_scenes(video_path: str) -> list[dict]:
    """
    Use PySceneDetect ContentDetector to find scene boundaries.
    Falls back to a single full-video scene if nothing is detected or if
    scenedetect is unavailable.
    """
    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector

        video = open_video(video_path)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=27.0))
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        scenes = [
            {"start": start.get_seconds(), "end": end.get_seconds()}
            for start, end in scene_list
        ]
        if scenes:
            return scenes

        logger.info("No scenes detected, falling back to full video")
    except ImportError:
        logger.warning("scenedetect not available, falling back to full video")
    except Exception as exc:
        logger.warning("Scene detection failed (%s), falling back to full video", exc)

    # Fallback: treat entire video as one scene
    duration = _probe_duration(video_path)
    return [{"start": 0.0, "end": duration}]


def _probe_duration(video_path: str) -> float:
    """
    Get video duration in seconds using ffprobe CLI (no ffmpeg-python dependency for probe).
    Falls back to 0.0 if ffprobe is unavailable.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", video_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(result.stdout)
        return float(data["format"]["duration"])
    except Exception as exc:
        logger.warning("ffprobe failed (%s), duration set to 0", exc)
        return 0.0


def _generate_subtitles(video_path: str) -> list[dict]:
    """
    Send the video file to OpenAI Whisper API for transcription.
    Returns a list of {start, end, text} dicts.
    Returns [] if OPENAI_API_KEY is not set (allows pipeline to continue without ASR).
    """
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set — skipping ASR, subtitles will be empty")
        return []

    from openai import OpenAI

    client = OpenAI(
        api_key=settings.OPENAI_API_KEY,
        base_url=settings.OPENAI_BASE_URL,
    )

    with open(video_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model=settings.WHISPER_MODEL,
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["segment"],
            language="zh",          # Chinese; set to None for auto-detect
        )

    subtitles = []
    if hasattr(transcript, "segments") and transcript.segments:
        for seg in transcript.segments:
            subtitles.append({
                "start": float(seg.start),
                "end": float(seg.end),
                "text": seg.text.strip(),
            })

    return subtitles


def _build_clip_plan(scenes: list[dict], subtitles: list[dict]) -> dict:
    """
    Merge scene boundaries with subtitle segments to produce a structured clip plan.
    Each segment gets the subtitle text whose time range overlaps with the scene.
    """
    segments = []
    for i, scene in enumerate(scenes):
        # Collect subtitles that overlap with this scene
        # Overlap condition: sub.start < scene.end AND sub.end > scene.start
        scene_subs = [
            s for s in subtitles
            if s["start"] < scene["end"] and s["end"] > scene["start"]
        ]
        transcript = " ".join(s["text"] for s in scene_subs).strip()
        segments.append({
            "id": i + 1,
            "start": round(scene["start"], 3),
            "end": round(scene["end"], 3),
            "duration": round(scene["end"] - scene["start"], 3),
            "transcript": transcript,
        })

    return {
        "segments": segments,
        "total_scenes": len(segments),
        "total_duration": round(sum(s["duration"] for s in segments), 3),
    }


def _write_srt(subtitles: list[dict], srt_path: str) -> bool:
    """
    Write subtitles to an SRT file.
    Returns True if the file was written with content, False if subtitles were empty.
    """
    if not subtitles:
        return False

    def _fmt(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, sub in enumerate(subtitles, start=1):
            f.write(f"{i}\n")
            f.write(f"{_fmt(sub['start'])} --> {_fmt(sub['end'])}\n")
            f.write(f"{sub['text']}\n\n")

    return True


def _render_video(
    input_path: str,
    scenes: list[dict],
    srt_path: str | None,
    output_path: str,
):
    """
    Use FFmpeg to:
      1. Concatenate selected scenes from the input video
      2. Optionally burn subtitles (if srt_path is given and non-empty)
    Output: H.264 + AAC MP4, preset=fast, CRF 23.

    Uses the ffmpeg CLI via subprocess (more portable than ffmpeg-python for concat+vf).
    """
    # Build a concat demuxer file
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as f:
        concat_file = f.name
        for scene in scenes:
            # ffmpeg concat demuxer: single-quoted paths
            safe_path = input_path.replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
            f.write(f"inpoint {scene['start']:.6f}\n")
            f.write(f"outpoint {scene['end']:.6f}\n")

    try:
        # Base ffmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file,
        ]

        # Video filter: optionally burn subtitles
        vf_parts = []
        if srt_path and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            # Escape special chars in the srt path for the subtitles filter
            escaped_srt = srt_path.replace("\\", "\\\\").replace(":", "\\:")
            vf_parts.append(
                f"subtitles={escaped_srt}:force_style='FontSize=20,"
                "PrimaryColour=&H00FFFFFF&,OutlineColour=&H00000000&,Outline=1'"
            )

        if vf_parts:
            cmd += ["-vf", ",".join(vf_parts)]

        cmd += [
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-movflags", "+faststart",  # web-friendly: moov atom at front
            output_path,
        ]

        logger.debug("FFmpeg command: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 min max
        )

        if result.returncode != 0:
            logger.error("FFmpeg stderr:\n%s", result.stderr[-2000:])
            raise RuntimeError(
                f"FFmpeg exited with code {result.returncode}. "
                f"Last error: {result.stderr[-500:]}"
            )

        logger.info("FFmpeg render OK → %s", output_path)

    finally:
        try:
            os.unlink(concat_file)
        except OSError:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Rerender task — skips scene-detection & ASR, uses existing clip_plan
# ─────────────────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=0,
    name="clip_task.rerender_clip_job",
)
def rerender_clip_job(self, job_id: str, video_id: str):
    """
    Re-render a clip job using the existing (possibly user-edited) clip_plan.
    Skips scene detection and ASR — just renders from the saved segments.
    """
    logger.info("Starting rerender job %s for video %s", job_id, video_id)

    try:
        _update_job(job_id, status="processing", progress=5)
        _publish(job_id, "progress", 5, "Starting re-render…")

        # Load clip_plan from DB
        engine = _make_sync_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT clip_plan FROM clip_jobs WHERE id=:id"),
                {"id": job_id},
            ).fetchone()
        if not row or not row[0]:
            raise ValueError(f"No clip_plan found for job {job_id}")

        raw = row[0]
        plan = json.loads(raw) if isinstance(raw, str) else raw
        segments = plan.get("segments", [])
        if not segments:
            raise ValueError("clip_plan has no segments")

        # Convert segments to scene dicts for _render_video
        scenes = [{"start": s["start"], "end": s["end"]} for s in segments]

        _publish(job_id, "progress", 10, "Downloading video…")
        storage_path = _fetch_video_storage_path(video_id)

        with tempfile.TemporaryDirectory(prefix="rerender_") as tmpdir:
            local_video = os.path.join(tmpdir, "input.mp4")
            from app.utils.storage import download_file
            download_file(storage_path, local_video)
            logger.info("Video downloaded to %s", local_video)

            _publish(job_id, "progress", 30, "Rebuilding subtitles…")
            # Rebuild SRT from plan transcript
            srt_path = os.path.join(tmpdir, "subtitles.srt")
            subtitle_list = [
                {"start": s["start"], "end": s["end"], "text": s.get("transcript", "")}
                for s in segments
                if s.get("transcript", "").strip()
            ]
            has_subs = _write_srt(subtitle_list, srt_path) if subtitle_list else False

            _publish(job_id, "progress", 50, "Rendering video…")
            output_local = os.path.join(tmpdir, "output.mp4")
            _render_video(local_video, scenes, srt_path if has_subs else None, output_local)
            out_size = os.path.getsize(output_local) if os.path.exists(output_local) else 0
            logger.info("Rerender complete: %s (%d bytes)", output_local, out_size)

            _publish(job_id, "progress", 90, "Uploading result…")
            output_object = f"outputs/{job_id}/output.mp4"
            from app.utils.storage import upload_file
            upload_file(output_object, output_local, content_type="video/mp4")

        _update_job(
            job_id,
            status="done",
            progress=100,
            clip_plan=plan,
            output_path=output_object,
        )
        _publish(job_id, "done", 100, "Re-render complete! Your clip is ready.")
        logger.info("Rerender job %s completed", job_id)

    except Exception as exc:
        logger.exception("Rerender job %s failed: %s", job_id, exc)
        _update_job(job_id, status="failed", progress=0, error_msg=str(exc))
        _publish(job_id, "error", -1, f"Rerender failed: {exc}")
        raise
