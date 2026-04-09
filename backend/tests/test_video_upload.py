import io
from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_upload_rejects_large_file_by_content_length(client, user_factory, auth_headers_factory, project_factory):
    user = await user_factory("upload@example.com")
    project = await project_factory(user, name="Upload Project")
    headers = auth_headers_factory(user)
    headers["content-length"] = str(501 * 1024 * 1024)

    resp = client.post(
        f"/api/videos/{project.id}/upload",
        headers=headers,
        files={"file": ("large.mp4", io.BytesIO(b"x"), "video/mp4")},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "File too large. Maximum size is 500MB"


@pytest.mark.asyncio
@patch("app.api.videos.save_uploaded_video")
async def test_upload_passes_size_limit_to_service(mock_save, client, user_factory, auth_headers_factory, project_factory):
    import datetime

    user = await user_factory("upload2@example.com")
    project = await project_factory(user, name="Upload Project 2")

    mock_save.return_value = type("V", (), {
        "id": "v1", "project_id": project.id, "filename": "ok.mp4",
        "source": "local", "storage_path": "videos/x/ok.mp4",
        "duration": 1.0, "created_at": datetime.datetime.utcnow(),
    })()

    resp = client.post(
        f"/api/videos/{project.id}/upload",
        headers=auth_headers_factory(user),
        files={"file": ("ok.mp4", io.BytesIO(b"small"), "video/mp4")},
    )
    assert resp.status_code == 200
    assert mock_save.call_args.kwargs["max_file_size"] == 500 * 1024 * 1024
