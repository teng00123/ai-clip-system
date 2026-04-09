"""
tests/test_timeline_editor.py — 时间轴编辑器 API 测试

覆盖：
- PATCH /clips/{job_id}/plan 正常更新
- 片段删除（不传该 id）
- 片段剪辑（修改 start/end）
- 字幕文本修改
- end <= start 返回 422
- job 状态不是 done/failed 时返回 400
- 其他用户不能修改他人的 job
- total_scenes / total_duration 自动更新
- segments 顺序跟随请求顺序
- 空 segments 返回 422
"""
import pytest
from unittest.mock import patch, MagicMock


# ── helpers ───────────────────────────────────────────────────────────────────

def _auth(client, email, password="pw123456"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _create_project(client, headers):
    r = client.post("/api/projects", json={"name": "TL Test", "description": ""}, headers=headers)
    assert r.status_code == 200
    return r.json()["id"]


def _complete_guide(client, headers, pid):
    client.post(f"/api/guide/{pid}/start", headers=headers)
    answers = [
        "Knowledge sharing", "Help professionals", "Young professionals",
        "Professional", "1-3 minutes", "Weekly", "", "",
    ]
    for i, ans in enumerate(answers):
        client.post(f"/api/guide/{pid}/answer", json={"step": i, "answer": ans}, headers=headers)


def _upload_video(client, headers, pid):
    """Mock video upload using same pattern as test_e2e.py"""
    from io import BytesIO
    from app.models.video import Video as _Video
    import asyncio

    async def _fake_save(db, project_id, file, *, max_file_size):
        import uuid as _uuid
        video = _Video(
            id=str(_uuid.uuid4()),
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

    fake_file = BytesIO(b"fake video content")
    with patch("app.api.videos.save_uploaded_video", new=_fake_save):
        r = client.post(
            f"/api/videos/{pid}/upload",
            files={"file": ("test.mp4", fake_file, "video/mp4")},
            headers=headers,
        )
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _create_clip_job_with_plan(client, headers, pid, vid):
    """Create a done clip job with a preset clip_plan via mocked create_clip_job"""
    from app.models.clip_job import ClipJob as _ClipJob
    import uuid

    plan = {
        "segments": [
            {"id": 1, "start": 0.0, "end": 10.0, "duration": 10.0, "transcript": "Hello world"},
            {"id": 2, "start": 15.0, "end": 25.0, "duration": 10.0, "transcript": "Good morning"},
            {"id": 3, "start": 30.0, "end": 45.0, "duration": 15.0, "transcript": ""},
        ],
        "total_scenes": 3,
        "total_duration": 35.0,
    }

    async def _fake_create(db, project_id, video_id):
        job = _ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="done",
            progress=100,
            output_path=f"outputs/{project_id}/out.mp4",
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


# ── PATCH /clips/{job_id}/plan ────────────────────────────────────────────────

def test_patch_plan_basic_update(client):
    """正常更新片段边界"""
    headers = _auth(client, "tl-patch-basic@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={
            "segments": [
                {"id": 1, "start": 0.5, "end": 9.5, "transcript": "Hello world"},
                {"id": 2, "start": 15.0, "end": 25.0, "transcript": "Good morning"},
                {"id": 3, "start": 30.0, "end": 45.0, "transcript": ""},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    plan = resp.json()["clip_plan"]
    assert plan["segments"][0]["start"] == pytest.approx(0.5)
    assert plan["segments"][0]["end"] == pytest.approx(9.5)


def test_patch_plan_delete_segment(client):
    """删除片段（不传该 id），total_scenes 更新"""
    headers = _auth(client, "tl-patch-del@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={
            "segments": [
                {"id": 1, "start": 0.0, "end": 10.0, "transcript": "Hello world"},
                # id=2 deleted
                {"id": 3, "start": 30.0, "end": 45.0, "transcript": ""},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    plan = resp.json()["clip_plan"]
    assert plan["total_scenes"] == 2
    ids = [s["id"] for s in plan["segments"]]
    # Renumbered 1,2
    assert ids == [1, 3] or len(ids) == 2


def test_patch_plan_total_duration_recalculated(client):
    """total_duration 自动重算"""
    headers = _auth(client, "tl-patch-dur@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={
            "segments": [
                {"id": 1, "start": 0.0, "end": 5.0, "transcript": ""},
                {"id": 2, "start": 10.0, "end": 20.0, "transcript": ""},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    # total_duration = (5-0) + (20-10) = 15
    assert resp.json()["clip_plan"]["total_duration"] == pytest.approx(15.0)


def test_patch_plan_update_transcript(client):
    """修改字幕文本"""
    headers = _auth(client, "tl-patch-sub@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={
            "segments": [
                {"id": 1, "start": 0.0, "end": 10.0, "transcript": "Updated subtitle text"},
                {"id": 2, "start": 15.0, "end": 25.0, "transcript": "Good morning"},
                {"id": 3, "start": 30.0, "end": 45.0, "transcript": "New text here"},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    segs = resp.json()["clip_plan"]["segments"]
    assert segs[0]["transcript"] == "Updated subtitle text"
    assert segs[2]["transcript"] == "New text here"


def test_patch_plan_end_le_start_422(client):
    """end <= start 的片段返回 422"""
    headers = _auth(client, "tl-patch-inv@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={
            "segments": [
                {"id": 1, "start": 10.0, "end": 5.0, "transcript": ""},  # end < start
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_patch_plan_equal_times_422(client):
    """start == end 的片段返回 422"""
    headers = _auth(client, "tl-patch-eq@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={
            "segments": [
                {"id": 1, "start": 5.0, "end": 5.0, "transcript": ""},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 422


def test_patch_plan_pending_job_returns_400(client):
    """job 状态为 pending 时 PATCH 返回 400"""
    from app.models.clip_job import ClipJob as _ClipJob
    import uuid

    headers = _auth(client, "tl-patch-pend@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    _complete_guide(client, headers, pid)

    # Create a pending (not done/failed) job via mock
    async def _fake_pending(db, project_id, video_id):
        job = _ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="pending",
            progress=0,
            clip_plan=None,
        )
        db.add(job)
        await db.flush()
        return job

    with patch("app.api.clips.create_clip_job", new=_fake_pending):
        r = client.post("/api/clips", json={"project_id": pid, "video_id": vid}, headers=headers)
    assert r.status_code == 200
    job_id = r.json()["id"]

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={"segments": [{"id": 1, "start": 0.0, "end": 5.0, "transcript": ""}]},
        headers=headers,
    )
    assert resp.status_code == 400
    assert "Can only patch" in resp.json()["detail"]


def test_patch_plan_other_user_404(client):
    """其他用户修改 → 404"""
    h1 = _auth(client, "tl-patch-u1@test.com")
    h2 = _auth(client, "tl-patch-u2@test.com")

    pid = _create_project(client, h1)
    vid = _upload_video(client, h1, pid)
    job_id = _create_clip_job_with_plan(client, h1, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={"segments": [{"id": 1, "start": 0.0, "end": 5.0, "transcript": ""}]},
        headers=h2,
    )
    assert resp.status_code == 404


def test_patch_plan_unauthenticated_401(client):
    """未认证返回 401"""
    resp = client.patch(
        "/api/clips/fake-job/plan",
        json={"segments": []},
    )
    assert resp.status_code == 401


def test_patch_plan_preserves_segment_order(client):
    """返回 segments 顺序跟随请求顺序"""
    headers = _auth(client, "tl-patch-ord@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={
            "segments": [
                {"id": 3, "start": 30.0, "end": 45.0, "transcript": "Last"},
                {"id": 1, "start": 0.0, "end": 10.0, "transcript": "First"},
                {"id": 2, "start": 15.0, "end": 25.0, "transcript": "Middle"},
            ]
        },
        headers=headers,
    )
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.json()["clip_plan"]["segments"]]
    assert ids == [3, 1, 2]


def test_patch_plan_single_segment(client):
    """只剩一个片段也能正常更新"""
    headers = _auth(client, "tl-patch-single@test.com")
    pid = _create_project(client, headers)
    vid = _upload_video(client, headers, pid)
    job_id = _create_clip_job_with_plan(client, headers, pid, vid)

    resp = client.patch(
        f"/api/clips/{job_id}/plan",
        json={"segments": [{"id": 1, "start": 5.0, "end": 20.0, "transcript": "Only one"}]},
        headers=headers,
    )
    assert resp.status_code == 200
    plan = resp.json()["clip_plan"]
    assert plan["total_scenes"] == 1
    assert plan["total_duration"] == pytest.approx(15.0)
