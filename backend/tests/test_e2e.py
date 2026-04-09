"""
End-to-End tests for ai-clip-system
====================================
These tests exercise the full user journey through the HTTP API using
FastAPI's TestClient.  External side-effects (MinIO, OpenAI, Redis) are
patched so the suite runs with no real infrastructure.

Test scenarios
--------------
1. Auth flow          – register, login, /me, duplicate email, bad password
2. Project lifecycle  – CRUD, status transitions
3. Guide flow         – start, answer all 8 questions, brief, re-start
4. Script flow        – block before guide done, generate, edit, rewrite, version bump
5. Video upload       – block oversized file, upload ok, list
6. Clip job flow      – block before guide done, submit, get, list, download URL
7. Full happy path    – one liner from register → clip job created
8. Cross-user isolation (complementary to unit authz tests)
"""

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.guide_service import TOTAL_STEPS

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _register(client, email="e2e@example.com", password="pw123456", nickname="E2E"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "nickname": nickname})
    assert r.status_code == 200, r.text
    return r.json()


def _auth(client, email="e2e@example.com", password="pw123456"):
    tok = _register(client, email, password)["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def _create_project(client, headers, name="E2E Project"):
    r = client.post("/api/projects", json={"name": name, "description": "desc"}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _complete_guide(client, headers, project_id):
    """Walks through all TOTAL_STEPS questions with canned answers."""
    client.post(f"/api/guide/{project_id}/start", headers=headers)
    for step in range(TOTAL_STEPS):
        r = client.get(f"/api/guide/{project_id}/question", headers=headers)
        assert r.status_code == 200, f"step {step}: {r.text}"
        q = r.json()
        answer = q["options"][0] if q["question_type"] == "single_choice" else "automated test answer"
        r2 = client.post(f"/api/guide/{project_id}/answer", json={"step": step, "answer": answer}, headers=headers)
        assert r2.status_code == 200, f"step {step} answer: {r2.text}"
    return client.get(f"/api/guide/{project_id}/brief", headers=headers).json()


FAKE_SCRIPT_CONTENT = {
    "title": "E2E Test Script",
    "hook": "This is a hook",
    "sections": [{"id": 1, "title": "Intro", "content": "Hello world", "duration_estimate": "10s"}],
    "cta": "Like and subscribe",
    "total_duration_estimate": "30s",
    "notes": "No notes",
}

FAKE_REWRITE = "Rewritten content via AI"


def _mock_generate_script():
    return patch(
        "app.api.scripts.generate_script",
        new=AsyncMock(return_value=FAKE_SCRIPT_CONTENT),
    )


def _mock_rewrite_section():
    return patch(
        "app.api.scripts.rewrite_section",
        new=AsyncMock(return_value=FAKE_REWRITE),
    )


def _mock_storage():
    """Patches MinIO calls wherever they are imported."""
    from contextlib import ExitStack
    from unittest.mock import patch, MagicMock

    class _MultiPatch:
        """Context manager that applies several patches at once."""
        def __init__(self):
            self._stack = ExitStack()

        def __enter__(self):
            targets = [
                ("app.utils.storage", dict(
                    ensure_bucket=MagicMock(),
                    upload_file=MagicMock(),
                    get_presigned_url=MagicMock(return_value="https://minio.test/signed"),
                    remove_object=MagicMock(),
                )),
                # patch the names as imported into each API module
                ("app.api.clips",    dict(get_presigned_url=MagicMock(return_value="https://minio.test/signed"))),
                ("app.api.projects", dict(remove_object=MagicMock())),
                ("app.api.videos",   dict(get_presigned_url=MagicMock(return_value="https://minio.test/signed"))),
            ]
            for module, attrs in targets:
                self._stack.enter_context(patch.multiple(module, **attrs))
            return self

        def __exit__(self, *args):
            self._stack.close()

    return _MultiPatch()


def _mock_clip_service():
    """Patches create_clip_job to return a done job immediately."""
    from app.models.clip_job import ClipJob as _ClipJob
    import uuid, datetime

    async def _fake_create(db, project_id, video_id):
        job = _ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="done",
            progress=100,
            output_path=f"outputs/{project_id}/out.mp4",
            clip_plan={"segments": [{"id": 1, "start": 0.0, "end": 5.0, "duration": 5.0, "transcript": "hello"}], "total_scenes": 1},
        )
        db.add(job)
        await db.flush()
        return job

    return patch("app.api.clips.create_clip_job", new=_fake_create)


def _mock_video_service():
    """Patches save_uploaded_video to skip real file I/O."""
    from app.models.video import Video as _Video

    async def _fake_save(db, project_id, file, *, max_file_size):
        video = _Video(
            id=f"vid-e2e",
            project_id=project_id,
            filename=file.filename or "test.mp4",
            source="local",
            storage_path=f"videos/{project_id}/test.mp4",
            duration=30.0,
            file_size="1024",
            metadata_={},
        )
        db.add(video)
        await db.flush()
        return video

    return patch("app.api.videos.save_uploaded_video", new=_fake_save)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Auth
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_and_login(client):
    tok = _register(client, "auth1@example.com")
    assert "access_token" in tok
    assert tok["user"]["email"] == "auth1@example.com"

    r = client.post("/api/auth/login", json={"email": "auth1@example.com", "password": "pw123456"})
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_duplicate_email_rejected(client):
    _register(client, "dup@example.com")
    r = client.post("/api/auth/register", json={"email": "dup@example.com", "password": "pw123456"})
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"]


@pytest.mark.asyncio
async def test_wrong_password_rejected(client):
    _register(client, "wrong@example.com")
    r = client.post("/api/auth/login", json={"email": "wrong@example.com", "password": "bad"})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_me_returns_current_user(client):
    h = _auth(client, "me@example.com")
    r = client.get("/api/auth/me", headers=h)
    assert r.status_code == 200
    assert r.json()["email"] == "me@example.com"


@pytest.mark.asyncio
async def test_unauthenticated_request_blocked(client):
    r = client.get("/api/projects")
    assert r.status_code == 401


# ─────────────────────────────────────────────────────────────────────────────
# 2. Project lifecycle
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_and_list_projects(client):
    h = _auth(client, "proj@example.com")
    p = _create_project(client, h, "My Project")
    assert p["name"] == "My Project"
    assert p["status"] == "draft"

    lst = client.get("/api/projects", headers=h).json()
    assert any(x["id"] == p["id"] for x in lst)


@pytest.mark.asyncio
async def test_delete_project(client):
    h = _auth(client, "del@example.com")
    p = _create_project(client, h)
    with _mock_storage():
        r = client.delete(f"/api/projects/{p['id']}", headers=h)
    assert r.status_code == 200
    assert r.json() == {"ok": True}


@pytest.mark.asyncio
async def test_cannot_access_other_users_project(client):
    h1 = _auth(client, "own@example.com")
    h2 = _auth(client, "att@example.com")
    p = _create_project(client, h1)
    r = client.get(f"/api/projects/{p['id']}", headers=h2)
    assert r.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 3. Guide flow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_guide_full_flow(client):
    h = _auth(client, "guide@example.com")
    p = _create_project(client, h)

    brief = _complete_guide(client, h, p["id"])
    assert "topic_category" in brief
    assert "summary" in brief

    # guide session should be marked completed
    r = client.post(f"/api/guide/{p['id']}/start", headers=h)
    assert r.json()["completed"] is True


@pytest.mark.asyncio
async def test_guide_question_sequence(client):
    h = _auth(client, "gseq@example.com")
    p = _create_project(client, h)
    client.post(f"/api/guide/{p['id']}/start", headers=h)

    r = client.get(f"/api/guide/{p['id']}/question", headers=h)
    q = r.json()
    assert q["step"] == 0
    assert q["total_steps"] == TOTAL_STEPS
    assert q["question_type"] in ("single_choice", "text_input")


@pytest.mark.asyncio
async def test_brief_blocked_before_guide_done(client):
    h = _auth(client, "bguide@example.com")
    p = _create_project(client, h)
    client.post(f"/api/guide/{p['id']}/start", headers=h)
    r = client.get(f"/api/guide/{p['id']}/brief", headers=h)
    assert r.status_code == 400
    assert "not completed" in r.json()["detail"]


@pytest.mark.asyncio
async def test_project_status_becomes_scripting_after_guide(client):
    h = _auth(client, "gstatus@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])
    proj = client.get(f"/api/projects/{p['id']}", headers=h).json()
    assert proj["status"] == "scripting"


# ─────────────────────────────────────────────────────────────────────────────
# 4. Script flow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_script_blocked_before_guide_done(client):
    h = _auth(client, "sblock@example.com")
    p = _create_project(client, h)
    client.post(f"/api/guide/{p['id']}/start", headers=h)
    with _mock_generate_script():
        r = client.post(f"/api/scripts/generate/{p['id']}", headers=h)
    assert r.status_code == 400
    assert "guide" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_and_get_script(client):
    h = _auth(client, "sgen@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_generate_script():
        r = client.post(f"/api/scripts/generate/{p['id']}", headers=h)
    assert r.status_code == 200
    s = r.json()
    assert s["content"]["title"] == "E2E Test Script"
    assert s["is_latest"] is True
    assert s["version"] == 1

    latest = client.get(f"/api/scripts/{p['id']}/latest", headers=h).json()
    assert latest["id"] == s["id"]


@pytest.mark.asyncio
async def test_script_version_bumps_on_regenerate(client):
    h = _auth(client, "sver@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_generate_script():
        r1 = client.post(f"/api/scripts/generate/{p['id']}", headers=h)
        r2 = client.post(f"/api/scripts/generate/{p['id']}", headers=h)
    assert r1.json()["version"] == 1
    assert r2.json()["version"] == 2

    # only latest is marked
    lst = client.get(f"/api/scripts/{p['id']}", headers=h).json()
    latest_count = sum(1 for s in lst if s["is_latest"])
    assert latest_count == 1


@pytest.mark.asyncio
async def test_update_script(client):
    h = _auth(client, "supd@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_generate_script():
        s = client.post(f"/api/scripts/generate/{p['id']}", headers=h).json()

    new_content = {**FAKE_SCRIPT_CONTENT, "title": "Updated Title"}
    r = client.patch(f"/api/scripts/{s['id']}", headers=h, json={"content": new_content})
    assert r.status_code == 200
    assert r.json()["content"]["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_rewrite_section(client):
    h = _auth(client, "srw@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_generate_script():
        s = client.post(f"/api/scripts/generate/{p['id']}", headers=h).json()

    with _mock_rewrite_section():
        r = client.post(
            f"/api/scripts/{s['id']}/rewrite-section",
            headers=h,
            json={"section_content": "old text", "instruction": "make it funnier"},
        )
    assert r.status_code == 200
    assert r.json()["rewritten"] == FAKE_REWRITE


# ─────────────────────────────────────────────────────────────────────────────
# 5. Video upload
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_rejects_non_video(client):
    h = _auth(client, "vtype@example.com")
    p = _create_project(client, h)
    with _mock_storage():
        r = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("bad.txt", io.BytesIO(b"hello"), "text/plain")},
        )
    assert r.status_code == 400
    assert "Unsupported" in r.json()["detail"]


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(client):
    h = _auth(client, "vsize@example.com")
    p = _create_project(client, h)
    big_headers = dict(h)
    big_headers["content-length"] = str(501 * 1024 * 1024)
    r = client.post(
        f"/api/videos/{p['id']}/upload",
        headers=big_headers,
        files={"file": ("big.mp4", io.BytesIO(b"x"), "video/mp4")},
    )
    assert r.status_code == 400
    assert "too large" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_upload_video_success(client):
    h = _auth(client, "vok@example.com")
    p = _create_project(client, h)
    with _mock_video_service():
        r = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("ok.mp4", io.BytesIO(b"fake video bytes"), "video/mp4")},
        )
    assert r.status_code == 200
    v = r.json()
    assert v["filename"] == "ok.mp4"
    assert v["project_id"] == p["id"]


@pytest.mark.asyncio
async def test_list_videos(client):
    h = _auth(client, "vlist@example.com")
    p = _create_project(client, h)
    with _mock_video_service():
        client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("ok.mp4", io.BytesIO(b"x"), "video/mp4")},
        )
    lst = client.get(f"/api/videos/{p['id']}", headers=h).json()
    assert len(lst) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 6. Clip job flow
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clip_blocked_before_guide_done(client):
    h = _auth(client, "cblock@example.com")
    p = _create_project(client, h)
    client.post(f"/api/guide/{p['id']}/start", headers=h)

    with _mock_video_service():
        v = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("v.mp4", io.BytesIO(b"x"), "video/mp4")},
        ).json()

    r = client.post("/api/clips", headers=h, json={"project_id": p["id"], "video_id": v["id"]})
    assert r.status_code == 400
    assert "guide" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_submit_clip_job(client):
    h = _auth(client, "csub@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_video_service():
        v = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("v.mp4", io.BytesIO(b"x"), "video/mp4")},
        ).json()

    with _mock_clip_service():
        r = client.post("/api/clips", headers=h, json={"project_id": p["id"], "video_id": v["id"]})
    assert r.status_code == 200
    job = r.json()
    assert job["status"] == "done"
    assert job["project_id"] == p["id"]


@pytest.mark.asyncio
async def test_duplicate_clip_job_rejected(client):
    h = _auth(client, "cdup@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_video_service():
        v = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("v.mp4", io.BytesIO(b"x"), "video/mp4")},
        ).json()

    # first job succeeds; second with status=processing should conflict
    # We submit the first with fake "processing" status by patching differently
    from app.models.clip_job import ClipJob as _ClipJob

    async def _processing_job(db, project_id, video_id):
        import uuid
        job = _ClipJob(
            id=str(uuid.uuid4()),
            project_id=project_id,
            video_id=video_id,
            status="processing",
            progress=10,
        )
        db.add(job)
        await db.flush()
        return job

    with patch("app.api.clips.create_clip_job", new=_processing_job):
        client.post("/api/clips", headers=h, json={"project_id": p["id"], "video_id": v["id"]})

    # second submit should hit 409
    r2 = client.post("/api/clips", headers=h, json={"project_id": p["id"], "video_id": v["id"]})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_get_clip_job_and_download_url(client):
    h = _auth(client, "cdl@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_video_service():
        v = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("v.mp4", io.BytesIO(b"x"), "video/mp4")},
        ).json()

    with _mock_clip_service(), _mock_storage():
        job = client.post("/api/clips", headers=h, json={"project_id": p["id"], "video_id": v["id"]}).json()
        r = client.get(f"/api/clips/{job['id']}", headers=h)
        assert r.status_code == 200

        dl = client.get(f"/api/clips/{job['id']}/download-url", headers=h)
        assert dl.status_code == 200
        assert "url" in dl.json()


@pytest.mark.asyncio
async def test_list_clip_jobs(client):
    h = _auth(client, "clst@example.com")
    p = _create_project(client, h)
    _complete_guide(client, h, p["id"])

    with _mock_video_service():
        v = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("v.mp4", io.BytesIO(b"x"), "video/mp4")},
        ).json()

    with _mock_clip_service():
        client.post("/api/clips", headers=h, json={"project_id": p["id"], "video_id": v["id"]})

    lst = client.get(f"/api/clips/project/{p['id']}", headers=h).json()
    assert len(lst) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 7. Full happy path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_happy_path(client):
    """
    register → create project → complete guide →
    generate script → upload video → submit clip job → get download URL
    """
    h = _auth(client, "happy@example.com")

    # project
    p = _create_project(client, h, "Happy Path Project")
    assert p["status"] == "draft"

    # guide
    brief = _complete_guide(client, h, p["id"])
    assert brief["summary"]

    # project status updated
    proj = client.get(f"/api/projects/{p['id']}", headers=h).json()
    assert proj["status"] == "scripting"

    # script
    with _mock_generate_script():
        s = client.post(f"/api/scripts/generate/{p['id']}", headers=h).json()
    assert s["version"] == 1

    # update script
    new_content = {**FAKE_SCRIPT_CONTENT, "title": "Happy Path Script"}
    client.patch(f"/api/scripts/{s['id']}", headers=h, json={"content": new_content})

    # upload video
    with _mock_video_service():
        v = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h,
            files={"file": ("happy.mp4", io.BytesIO(b"fake"), "video/mp4")},
        ).json()
    assert v["filename"] == "happy.mp4"

    # clip job
    with _mock_clip_service(), _mock_storage():
        job = client.post(
            "/api/clips", headers=h,
            json={"project_id": p["id"], "video_id": v["id"]},
        ).json()
    assert job["status"] == "done"
    assert job["clip_plan"]["total_scenes"] == 1

    # download url
    with _mock_storage():
        dl = client.get(f"/api/clips/{job['id']}/download-url", headers=h).json()
    assert dl["url"].startswith("https://")

    # final project status
    proj = client.get(f"/api/projects/{p['id']}", headers=h).json()
    assert proj["status"] == "clipping"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Cross-user isolation (deeper coverage beyond unit tests)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cannot_read_other_users_guide(client):
    h1 = _auth(client, "gown@example.com")
    h2 = _auth(client, "gatt@example.com")
    p = _create_project(client, h1)
    client.post(f"/api/guide/{p['id']}/start", headers=h1)
    r = client.get(f"/api/guide/{p['id']}/question", headers=h2)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cannot_submit_answer_to_other_users_guide(client):
    h1 = _auth(client, "gown2@example.com")
    h2 = _auth(client, "gatt2@example.com")
    p = _create_project(client, h1)
    client.post(f"/api/guide/{p['id']}/start", headers=h1)
    r = client.post(f"/api/guide/{p['id']}/answer", headers=h2, json={"step": 0, "answer": "x"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cannot_generate_script_for_other_users_project(client):
    h1 = _auth(client, "sown@example.com")
    h2 = _auth(client, "satt@example.com")
    p = _create_project(client, h1)
    _complete_guide(client, h1, p["id"])
    with _mock_generate_script():
        r = client.post(f"/api/scripts/generate/{p['id']}", headers=h2)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_cannot_get_clip_job_of_other_user(client):
    h1 = _auth(client, "jown@example.com")
    h2 = _auth(client, "jatt@example.com")
    p = _create_project(client, h1)
    _complete_guide(client, h1, p["id"])

    with _mock_video_service():
        v = client.post(
            f"/api/videos/{p['id']}/upload",
            headers=h1,
            files={"file": ("v.mp4", io.BytesIO(b"x"), "video/mp4")},
        ).json()

    with _mock_clip_service():
        job = client.post("/api/clips", headers=h1, json={"project_id": p["id"], "video_id": v["id"]}).json()

    r = client.get(f"/api/clips/{job['id']}", headers=h2)
    assert r.status_code == 404
