from unittest.mock import patch

import pytest


@pytest.mark.asyncio
@patch("app.api.projects.remove_object")
async def test_delete_project_cleans_related_records_and_storage(
    mock_remove,
    client, db, user_factory, auth_headers_factory,
    project_factory, guide_session_factory, script_factory,
    video_factory, clip_job_factory,
):
    user = await user_factory("cleanup@example.com")
    project = await project_factory(user, name="Cleanup Project")
    await guide_session_factory(project, completed=True, step=8, brief={"summary": "ok"})
    await script_factory(project)
    video = await video_factory(project, filename="cleanup.mp4")
    job = await clip_job_factory(project, video, status="done", output_path="outputs/job/output.mp4")

    resp = client.delete(f"/api/projects/{project.id}", headers=auth_headers_factory(user))
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    removed_paths = {call.args[0] for call in mock_remove.call_args_list}
    assert video.storage_path in removed_paths
    assert job.output_path in removed_paths
