"""
tests/test_rerender.py — 重渲染 API 测试

覆盖：
- POST /clips/{job_id}/rerender 正常触发（done job）
- failed 状态也允许重渲染
- pending/processing 状态返回 400
- clip_plan 为空返回 400
- 其他用户返回 404
- 未认证返回 401
- 重渲染后 job 状态变为 pending
- Celery task 被调用一次
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.models.clip_job import ClipJob


# ── helpers ───────────────────────────────────────────────────────────────────

def _auth(client, email, password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_project(client, headers):
    r = client.post("/api/projects", json={"name": "Rerender Test", "description": ""}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


def _upload_video(client, headers, pid):
    from io import BytesIO
    import uuid

    async def _fake_save(db, project_id, file, *, max_file_size):
        from app.models.video import Video as _Video
        video = _Video(
            id=str(uuid.uuid4()),
            project_id=project_id,
            filename=file.filename or "test.mp4",
            source="local",
            storage_path=f"videos/{project_id}/test.mp4",
            duration=120.0,
            file_size="1024",
            metadata_={},
        )
        db.add(video)
        await db.flush()
        return video

    fake_file = BytesIO(b"fake")
    with patch("app.api.videos.save_uploaded_video", new=_fake_save):
        r = client.post(
            f"/api/videos/{pid}/upload",
            files={"file": ("test.mp4", fake_file, "video/mp4")},
            headers=headers,
        )
    assert r.status_code == 200
    return r.json()["id"]


def _complete_guide(client, headers, pid):
    client.post(f"/api/guide/{pid}/start", headers=headers)
    answers = ["Topic", "Purpose", "Audience", "Tone", "1-3m", "Weekly", "", ""]
    for i, ans in enumerate(answers):
        client.post(f"/api/guide/{pid}/answer", json={"step": i, "answer": ans}, headers=headers)


_PRESET_PLAN = {
    "segments": [
        {"id": 1, "start": 0.0, "end": 10.0, "duration": 10.0, "transcript": "Hello"},
        {"id": 2, "start": 15.0, "end": 25.0, "duration": 10.0, "transcript": "World"},
    ],
    "total_scenes": 2,
    "total_duration": 20.0,
}


def _create_job_with_status(client, headers, pid, vid, status: str, plan=_PRESET_PLAN):
    """Create a clip job with given status and plan."""
    import uuid

    async def _fake_create(db, project_id, video_id):
        job = ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status=status,
            progress=100 if status == "done" else 0,
            output_path=f"outputs/{project_id}/out.mp4" if status == "done" else None,
            clip_plan=plan,
        )
        db.add(job)
        await db.flush()
        return job

    _complete_guide(client, headers, pid)
    with patch("app.api.clips.create_clip_job", new=_fake_create):
        r = client.post("/api/clips", json={"project_id": pid, "video_id": vid}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


# ── tests ─────────────────────────────────────────────────────────────────────

def test_rerender_done_job_returns_pending(client):
    """done job 重渲染后状态变为 pending"""
    headers = _auth(client, "rr-done@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_job_with_status(client, headers, pid, vid, "done")

    with patch("app.api.clips.rerender_clip_job") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_rerender_dispatches_celery_task(client):
    """确认 Celery task 被调用一次"""
    headers = _auth(client, "rr-celery@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_job_with_status(client, headers, pid, vid, "done")

    with patch("app.api.clips.rerender_clip_job") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)

    assert resp.status_code == 200
    mock_task.delay.assert_called_once_with(job_id, vid)


def test_rerender_failed_job_allowed(client):
    """failed 状态也允许重渲染"""
    headers = _auth(client, "rr-failed@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_job_with_status(client, headers, pid, vid, "failed")

    with patch("app.api.clips.rerender_clip_job") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"


def test_rerender_pending_job_returns_400(client):
    """pending 状态返回 400"""
    import uuid

    headers = _auth(client, "rr-pending@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)

    async def _fake_pending(db, project_id, video_id):
        job = ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="pending",
            progress=0,
            clip_plan=_PRESET_PLAN,
        )
        db.add(job)
        await db.flush()
        return job

    _complete_guide(client, headers, pid)
    with patch("app.api.clips.create_clip_job", new=_fake_pending):
        r = client.post("/api/clips", json={"project_id": pid, "video_id": vid}, headers=headers)
    job_id = r.json()["id"]

    resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)
    assert resp.status_code == 400
    assert "Can only rerender" in resp.json()["detail"]


def test_rerender_processing_job_returns_400(client):
    """processing 状态返回 400"""
    import uuid

    headers = _auth(client, "rr-proc@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)

    async def _fake_proc(db, project_id, video_id):
        job = ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="processing",
            progress=50,
            clip_plan=_PRESET_PLAN,
        )
        db.add(job)
        await db.flush()
        return job

    _complete_guide(client, headers, pid)
    with patch("app.api.clips.create_clip_job", new=_fake_proc):
        r = client.post("/api/clips", json={"project_id": pid, "video_id": vid}, headers=headers)
    job_id = r.json()["id"]

    resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)
    assert resp.status_code == 400


def test_rerender_no_plan_returns_400(client):
    """clip_plan 为空返回 400"""
    import uuid

    headers = _auth(client, "rr-noplan@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)

    async def _fake_no_plan(db, project_id, video_id):
        job = ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="done",
            progress=100,
            clip_plan=None,  # 无 plan
        )
        db.add(job)
        await db.flush()
        return job

    _complete_guide(client, headers, pid)
    with patch("app.api.clips.create_clip_job", new=_fake_no_plan):
        r = client.post("/api/clips", json={"project_id": pid, "video_id": vid}, headers=headers)
    job_id = r.json()["id"]

    resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower() or "clip_plan" in resp.json()["detail"]


def test_rerender_other_user_404(client):
    """其他用户的 job 返回 404"""
    h1 = _auth(client, "rr-u1@test.com")
    h2 = _auth(client, "rr-u2@test.com")

    pid = _create_project(client, h1)
    vid = _upload_video(client, h1, pid)
    job_id = _create_job_with_status(client, h1, pid, vid, "done")

    resp = client.post(f"/api/clips/{job_id}/rerender", headers=h2)
    assert resp.status_code == 404


def test_rerender_unauthenticated_401(client):
    """未认证返回 401"""
    resp = client.post("/api/clips/fake-id/rerender")
    assert resp.status_code == 401


def test_rerender_resets_progress_to_zero(client):
    """重渲染后 progress 归零"""
    headers = _auth(client, "rr-progress@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_job_with_status(client, headers, pid, vid, "done")

    with patch("app.api.clips.rerender_clip_job") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["progress"] == 0


def test_rerender_clears_error_msg(client):
    """重渲染后 error_msg 清空"""
    import uuid

    headers = _auth(client, "rr-errmsg@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)

    async def _fake_failed_with_err(db, project_id, video_id):
        job = ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="failed",
            progress=0,
            error_msg="Previous error",
            clip_plan=_PRESET_PLAN,
        )
        db.add(job)
        await db.flush()
        return job

    _complete_guide(client, headers, pid)
    with patch("app.api.clips.create_clip_job", new=_fake_failed_with_err):
        r = client.post("/api/clips", json={"project_id": pid, "video_id": vid}, headers=headers)
    job_id = r.json()["id"]

    with patch("app.api.clips.rerender_clip_job") as mock_task:
        mock_task.delay = MagicMock()
        resp = client.post(f"/api/clips/{job_id}/rerender", headers=headers)

    assert resp.status_code == 200
    # error_msg should be None after reset
    assert resp.json().get("error_msg") is None
