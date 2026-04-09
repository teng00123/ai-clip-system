from unittest.mock import AsyncMock, patch

import pytest
from starlette.websockets import WebSocketDisconnect


@pytest.mark.asyncio
async def test_cannot_access_other_users_project_videos(client, user_factory, auth_headers_factory, project_factory, video_factory):
    owner = await user_factory("owner@example.com")
    attacker = await user_factory("attacker@example.com")
    project = await project_factory(owner, name="Owner Project")
    video = await video_factory(project)

    resp = client.get(f"/api/videos/{project.id}/{video.id}/url", headers=auth_headers_factory(attacker))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Project not found"


@pytest.mark.asyncio
async def test_cannot_update_other_users_script(client, user_factory, auth_headers_factory, project_factory, script_factory):
    owner = await user_factory("owner2@example.com")
    attacker = await user_factory("attacker2@example.com")
    project = await project_factory(owner, name="Script Owner")
    script = await script_factory(project)

    resp = client.patch(
        f"/api/scripts/{script.id}",
        headers=auth_headers_factory(attacker),
        json={"content": {"title": "x", "hook": "x", "sections": [], "cta": "x",
                          "total_duration_estimate": "30s", "notes": "x"}},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Script not found"


@pytest.mark.asyncio
async def test_clip_job_requires_completed_guide(
    client, user_factory, auth_headers_factory, project_factory, guide_session_factory, video_factory
):
    user = await user_factory("clip@example.com")
    project = await project_factory(user, name="Clip Project")
    await guide_session_factory(project, completed=False, step=3)
    video = await video_factory(project)

    resp = client.post(
        "/api/clips",
        headers=auth_headers_factory(user),
        json={"project_id": project.id, "video_id": video.id},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Complete the guide session before starting clip generation"


@pytest.mark.asyncio
async def test_duplicate_active_clip_job_returns_409(
    client, user_factory, auth_headers_factory, project_factory,
    guide_session_factory, video_factory, clip_job_factory,
):
    user = await user_factory("dup@example.com")
    project = await project_factory(user, name="Dup Project")
    await guide_session_factory(project, completed=True, step=8, brief={"summary": "ok"})
    video = await video_factory(project)
    await clip_job_factory(project, video, status="processing")

    resp = client.post(
        "/api/clips",
        headers=auth_headers_factory(user),
        json={"project_id": project.id, "video_id": video.id},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "A clip job is already running for this video"


@pytest.mark.asyncio
@patch("app.api.ws.aioredis.from_url")
@patch("app.api.ws._user_can_access_clip_job", new_callable=AsyncMock)
async def test_websocket_rejects_forbidden_job(mock_access, mock_redis, client, user_factory, auth_headers_factory):
    user = await user_factory("ws@example.com")
    token = auth_headers_factory(user)["Authorization"].split(" ", 1)[1]
    mock_access.return_value = False
    mock_redis.return_value = None

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect(f"/ws/clip/job-999?token={token}"):
            pass
    assert exc_info.value.code == 1008
