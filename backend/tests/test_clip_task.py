"""
Tests for clip_task.py
=======================
Covers:
  - _detect_scenes: normal + fallback when scenedetect returns empty
  - _probe_duration: ffprobe success + failure fallback
  - _generate_subtitles: no api key → skip; with key → parse segments
  - _build_clip_plan: overlap logic, empty subtitles
  - _write_srt: content + empty case
  - _render_video: subprocess command shape, subtitle on/off
  - process_clip_job (integration): happy path, failure path, DB updates
"""

import json
import os
import tempfile
from unittest.mock import MagicMock, patch, call

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# _probe_duration
# ─────────────────────────────────────────────────────────────────────────────

class TestProbeDuration:
    def test_happy_path(self, tmp_path):
        from app.tasks.clip_task import _probe_duration
        fake_output = json.dumps({"format": {"duration": "123.456"}})
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output, returncode=0)
            result = _probe_duration(str(tmp_path / "v.mp4"))
        assert abs(result - 123.456) < 0.001

    def test_fallback_on_error(self, tmp_path):
        from app.tasks.clip_task import _probe_duration
        with patch("subprocess.run", side_effect=FileNotFoundError("ffprobe not found")):
            result = _probe_duration(str(tmp_path / "v.mp4"))
        assert result == 0.0

    def test_fallback_on_bad_json(self, tmp_path):
        from app.tasks.clip_task import _probe_duration
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="not-json", returncode=0)
            result = _probe_duration(str(tmp_path / "v.mp4"))
        assert result == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# _detect_scenes
# ─────────────────────────────────────────────────────────────────────────────

def _make_fake_scenedetect(scene_list):
    """
    Build a fake scenedetect module tree and inject into sys.modules so that
    the `from scenedetect import ...` inside _detect_scenes uses mocks instead
    of the real library (which requires libGL.so.1).
    """
    import sys
    import types

    def _tc(seconds):
        m = MagicMock()
        m.get_seconds.return_value = float(seconds)
        return m

    # Build fake module objects
    fake_sd = types.ModuleType("scenedetect")
    fake_sm_instance = MagicMock()
    fake_sm_instance.get_scene_list.return_value = scene_list
    fake_sm_class = MagicMock(return_value=fake_sm_instance)

    fake_sd.open_video = MagicMock(return_value=MagicMock())
    fake_sd.SceneManager = fake_sm_class

    fake_detectors = types.ModuleType("scenedetect.detectors")
    fake_detectors.ContentDetector = MagicMock()

    # Patch sys.modules
    originals = {
        "scenedetect": sys.modules.get("scenedetect"),
        "scenedetect.detectors": sys.modules.get("scenedetect.detectors"),
    }
    sys.modules["scenedetect"] = fake_sd
    sys.modules["scenedetect.detectors"] = fake_detectors
    return originals, fake_sm_instance


def _restore_scenedetect(originals):
    import sys
    for k, v in originals.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


class TestDetectScenes:
    def test_returns_scenes_from_scenedetect(self, tmp_path):
        from app.tasks.clip_task import _detect_scenes

        def _tc(s):
            m = MagicMock(); m.get_seconds.return_value = float(s); return m

        originals, _ = _make_fake_scenedetect([
            (_tc(0.0), _tc(5.0)),
            (_tc(5.0), _tc(10.0)),
        ])
        try:
            scenes = _detect_scenes(str(tmp_path / "v.mp4"))
        finally:
            _restore_scenedetect(originals)

        assert len(scenes) == 2
        assert scenes[0] == {"start": 0.0, "end": 5.0}
        assert scenes[1] == {"start": 5.0, "end": 10.0}

    def test_fallback_when_no_scenes_detected(self, tmp_path):
        from app.tasks.clip_task import _detect_scenes

        originals, _ = _make_fake_scenedetect([])  # empty scene list
        try:
            with patch("app.tasks.clip_task._probe_duration", return_value=42.0):
                scenes = _detect_scenes(str(tmp_path / "v.mp4"))
        finally:
            _restore_scenedetect(originals)

        assert scenes == [{"start": 0.0, "end": 42.0}]

    def test_fallback_when_import_fails(self, tmp_path):
        """When scenedetect is not importable, fall back to full-video scene."""
        import sys
        from app.tasks.clip_task import _detect_scenes

        import types
        broken = types.ModuleType("scenedetect")

        def _raise(*a, **k):
            raise ImportError("libGL.so.1: cannot open")

        broken.open_video = _raise

        originals = {
            "scenedetect": sys.modules.get("scenedetect"),
            "scenedetect.detectors": sys.modules.get("scenedetect.detectors"),
        }
        sys.modules["scenedetect"] = broken
        sys.modules.pop("scenedetect.detectors", None)
        try:
            with patch("app.tasks.clip_task._probe_duration", return_value=15.0):
                scenes = _detect_scenes(str(tmp_path / "v.mp4"))
        finally:
            _restore_scenedetect(originals)

        assert scenes == [{"start": 0.0, "end": 15.0}]

    def test_fallback_when_scenedetect_raises(self, tmp_path):
        from app.tasks.clip_task import _detect_scenes

        def _tc(s):
            m = MagicMock(); m.get_seconds.return_value = float(s); return m

        originals, sm_instance = _make_fake_scenedetect([])
        # Make detect_scenes itself raise
        sm_instance.detect_scenes.side_effect = RuntimeError("GPU error")
        try:
            with patch("app.tasks.clip_task._probe_duration", return_value=20.0):
                scenes = _detect_scenes(str(tmp_path / "v.mp4"))
        finally:
            _restore_scenedetect(originals)

        assert scenes == [{"start": 0.0, "end": 20.0}]


# ─────────────────────────────────────────────────────────────────────────────
# _generate_subtitles
# ─────────────────────────────────────────────────────────────────────────────

class TestGenerateSubtitles:
    def test_returns_empty_when_no_api_key(self, tmp_path):
        from app.tasks.clip_task import _generate_subtitles
        with patch("app.tasks.clip_task.settings") as mock_settings:
            mock_settings.OPENAI_API_KEY = ""
            result = _generate_subtitles(str(tmp_path / "v.mp4"))
        assert result == []

    def test_parses_whisper_response(self, tmp_path):
        from app.tasks.clip_task import _generate_subtitles

        fake_video = tmp_path / "v.mp4"
        fake_video.write_bytes(b"fake")

        seg1 = MagicMock(start=0.0, end=3.5, text="  Hello world  ")
        seg2 = MagicMock(start=3.5, end=7.0, text="  How are you  ")
        fake_transcript = MagicMock(segments=[seg1, seg2])

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = fake_transcript

        with patch("app.tasks.clip_task.settings") as mock_settings, \
             patch("openai.OpenAI", return_value=mock_client):
            mock_settings.OPENAI_API_KEY = "sk-test"
            mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
            mock_settings.WHISPER_MODEL = "whisper-1"
            result = _generate_subtitles(str(fake_video))

        assert len(result) == 2
        assert result[0] == {"start": 0.0, "end": 3.5, "text": "Hello world"}
        assert result[1] == {"start": 3.5, "end": 7.0, "text": "How are you"}

    def test_returns_empty_when_no_segments(self, tmp_path):
        from app.tasks.clip_task import _generate_subtitles

        fake_video = tmp_path / "v.mp4"
        fake_video.write_bytes(b"fake")

        fake_transcript = MagicMock()
        del fake_transcript.segments  # simulate missing attribute

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = fake_transcript

        with patch("app.tasks.clip_task.settings") as mock_settings, \
             patch("openai.OpenAI", return_value=mock_client):
            mock_settings.OPENAI_API_KEY = "sk-test"
            mock_settings.OPENAI_BASE_URL = "https://api.openai.com/v1"
            mock_settings.WHISPER_MODEL = "whisper-1"
            result = _generate_subtitles(str(fake_video))

        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# _build_clip_plan
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildClipPlan:
    def test_basic_plan(self):
        from app.tasks.clip_task import _build_clip_plan
        scenes = [{"start": 0.0, "end": 5.0}, {"start": 5.0, "end": 10.0}]
        subtitles = [
            {"start": 0.5, "end": 2.0, "text": "Hello"},
            {"start": 2.5, "end": 4.5, "text": "World"},
            {"start": 6.0, "end": 8.0, "text": "Bye"},
        ]
        plan = _build_clip_plan(scenes, subtitles)
        assert plan["total_scenes"] == 2
        segs = plan["segments"]
        assert segs[0]["transcript"] == "Hello World"
        assert segs[1]["transcript"] == "Bye"
        assert segs[0]["id"] == 1
        assert segs[1]["id"] == 2

    def test_overlap_boundary(self):
        """Subtitle that straddles a scene boundary appears in the scene it overlaps most."""
        from app.tasks.clip_task import _build_clip_plan
        scenes = [{"start": 0.0, "end": 5.0}]
        # sub starts at 4.5, ends at 6.0 — overlaps with scene [0,5)
        subtitles = [{"start": 4.5, "end": 6.0, "text": "Overlap"}]
        plan = _build_clip_plan(scenes, subtitles)
        assert plan["segments"][0]["transcript"] == "Overlap"

    def test_empty_subtitles(self):
        from app.tasks.clip_task import _build_clip_plan
        scenes = [{"start": 0.0, "end": 10.0}]
        plan = _build_clip_plan(scenes, [])
        assert plan["segments"][0]["transcript"] == ""
        assert plan["total_scenes"] == 1

    def test_total_duration(self):
        from app.tasks.clip_task import _build_clip_plan
        scenes = [{"start": 0.0, "end": 3.0}, {"start": 3.0, "end": 7.0}]
        plan = _build_clip_plan(scenes, [])
        assert abs(plan["total_duration"] - 7.0) < 0.01


# ─────────────────────────────────────────────────────────────────────────────
# _write_srt
# ─────────────────────────────────────────────────────────────────────────────

class TestWriteSrt:
    def test_writes_valid_srt(self, tmp_path):
        from app.tasks.clip_task import _write_srt
        srt = tmp_path / "out.srt"
        subtitles = [
            {"start": 0.0, "end": 1.5, "text": "Hello"},
            {"start": 1.5, "end": 3.0, "text": "World"},
        ]
        result = _write_srt(subtitles, str(srt))
        assert result is True
        content = srt.read_text()
        assert "1\n" in content
        assert "Hello\n" in content
        assert "00:00:00,000 --> 00:00:01,500" in content

    def test_empty_subtitles_returns_false(self, tmp_path):
        from app.tasks.clip_task import _write_srt
        srt = tmp_path / "out.srt"
        result = _write_srt([], str(srt))
        assert result is False
        assert not srt.exists()

    def test_timestamp_formatting(self, tmp_path):
        from app.tasks.clip_task import _write_srt
        srt = tmp_path / "out.srt"
        _write_srt([{"start": 3661.75, "end": 3665.0, "text": "test"}], str(srt))
        content = srt.read_text()
        assert "01:01:01,750 --> 01:01:05,000" in content


# ─────────────────────────────────────────────────────────────────────────────
# _render_video
# ─────────────────────────────────────────────────────────────────────────────

class TestRenderVideo:
    def _run_render(self, scenes, srt_path=None, returncode=0):
        from app.tasks.clip_task import _render_video
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_input = os.path.join(tmpdir, "in.mp4")
            fake_output = os.path.join(tmpdir, "out.mp4")
            open(fake_input, "w").close()

            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=returncode,
                    stderr="some ffmpeg output",
                )
                _render_video(fake_input, scenes, srt_path, fake_output)
                return mock_run.call_args[0][0]  # the cmd list

    def test_basic_command_shape(self):
        scenes = [{"start": 0.0, "end": 5.0}]
        cmd = self._run_render(scenes)
        assert cmd[0] == "ffmpeg"
        assert "-f" in cmd and "concat" in cmd
        assert "libx264" in cmd
        assert "aac" in cmd
        assert "+faststart" in cmd

    def test_no_subtitle_filter_when_srt_is_none(self):
        scenes = [{"start": 0.0, "end": 5.0}]
        cmd = self._run_render(scenes, srt_path=None)
        assert "-vf" not in cmd

    def test_subtitle_filter_added_when_srt_given(self, tmp_path):
        srt = tmp_path / "sub.srt"
        srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n\n")
        scenes = [{"start": 0.0, "end": 5.0}]
        cmd = self._run_render(scenes, srt_path=str(srt))
        assert "-vf" in cmd
        vf_val = cmd[cmd.index("-vf") + 1]
        assert "subtitles=" in vf_val

    def test_raises_on_nonzero_returncode(self):
        from app.tasks.clip_task import _render_video
        scenes = [{"start": 0.0, "end": 5.0}]
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_in = os.path.join(tmpdir, "in.mp4")
            fake_out = os.path.join(tmpdir, "out.mp4")
            open(fake_in, "w").close()
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1,
                    stderr="encoder error: codec not found",
                )
                with pytest.raises(RuntimeError, match="FFmpeg exited"):
                    _render_video(fake_in, scenes, None, fake_out)


# ─────────────────────────────────────────────────────────────────────────────
# process_clip_job  (integration — full pipeline mocked)
# ─────────────────────────────────────────────────────────────────────────────

FAKE_JOB_ID = "job-abc-123"
FAKE_VIDEO_ID = "vid-xyz-456"
FAKE_SCENES = [{"start": 0.0, "end": 5.0}, {"start": 5.0, "end": 10.0}]
FAKE_SUBS = [{"start": 0.5, "end": 2.0, "text": "Hello"}, {"start": 6.0, "end": 8.0, "text": "World"}]
FAKE_CLIP_PLAN = {
    "segments": [
        {"id": 1, "start": 0.0, "end": 5.0, "duration": 5.0, "transcript": "Hello"},
        {"id": 2, "start": 5.0, "end": 10.0, "duration": 5.0, "transcript": "World"},
    ],
    "total_scenes": 2,
    "total_duration": 10.0,
}


def _all_mocks(fake_scenes=FAKE_SCENES, fake_subs=FAKE_SUBS):
    """Returns a context manager that patches all external deps for the full task."""
    import contextlib

    class _Stack:
        def __enter__(self):
            self._stack = contextlib.ExitStack()
            self.patches = {}

            def _fake_download(object_name, dest_path):
                """Create the dest file so os.path.getsize() doesn't blow up."""
                open(dest_path, "wb").close()

            configs = {
                "app.tasks.clip_task._fetch_video_storage_path":
                    MagicMock(return_value="videos/proj/v.mp4"),
                "app.tasks.clip_task._update_job": MagicMock(),
                "app.tasks.clip_task._publish": MagicMock(),
                "app.tasks.clip_task._detect_scenes": MagicMock(return_value=fake_scenes),
                "app.tasks.clip_task._generate_subtitles": MagicMock(return_value=fake_subs),
                "app.tasks.clip_task._render_video": MagicMock(),
                "app.utils.storage.download_file": MagicMock(side_effect=_fake_download),
                "app.utils.storage.upload_file": MagicMock(return_value="outputs/job/output.mp4"),
            }
            for target, mock in configs.items():
                self.patches[target.split(".")[-1]] = self._stack.enter_context(
                    patch(target, mock)
                )
            return self

        def __exit__(self, *a):
            self._stack.close()

    return _Stack()


class TestProcessClipJob:
    def test_happy_path_calls_correct_sequence(self):
        from app.tasks.clip_task import process_clip_job

        with _all_mocks() as m:
            process_clip_job(FAKE_JOB_ID, FAKE_VIDEO_ID)

        # Verify key steps called
        m.patches["_fetch_video_storage_path"].assert_called_once_with(FAKE_VIDEO_ID)
        m.patches["_detect_scenes"].assert_called_once()
        m.patches["_generate_subtitles"].assert_called_once()
        m.patches["_render_video"].assert_called_once()
        m.patches["upload_file"].assert_called_once()

    def test_final_db_update_is_done(self):
        from app.tasks.clip_task import process_clip_job

        with _all_mocks() as m:
            process_clip_job(FAKE_JOB_ID, FAKE_VIDEO_ID)

        # Last _update_job call must set status=done progress=100
        calls = m.patches["_update_job"].call_args_list
        final_call_kwargs = calls[-1].kwargs
        assert final_call_kwargs["status"] == "done"
        assert final_call_kwargs["progress"] == 100
        assert final_call_kwargs["output_path"] is not None

    def test_progress_published_at_key_steps(self):
        from app.tasks.clip_task import process_clip_job

        with _all_mocks() as m:
            process_clip_job(FAKE_JOB_ID, FAKE_VIDEO_ID)

        publish_calls = m.patches["_publish"].call_args_list
        progress_values = [c.args[2] for c in publish_calls]
        # Must go up monotonically (or at least include 100 at end)
        assert 100 in progress_values
        assert publish_calls[-1].args[1] == "done"

    def test_failure_marks_job_failed(self):
        from app.tasks.clip_task import process_clip_job

        with _all_mocks() as m:
            # Make scene detection blow up
            m.patches["_detect_scenes"].side_effect = RuntimeError("GPU exploded")
            with pytest.raises(RuntimeError):
                process_clip_job(FAKE_JOB_ID, FAKE_VIDEO_ID)

        # _update_job must have been called with status=failed
        calls = m.patches["_update_job"].call_args_list
        failed_call = next(
            (c for c in calls if c.kwargs.get("status") == "failed"),
            None,
        )
        assert failed_call is not None
        assert "GPU exploded" in failed_call.kwargs.get("error_msg", "")

    def test_failure_publishes_error_event(self):
        from app.tasks.clip_task import process_clip_job

        with _all_mocks() as m:
            m.patches["_detect_scenes"].side_effect = ValueError("bad video")
            with pytest.raises(ValueError):
                process_clip_job(FAKE_JOB_ID, FAKE_VIDEO_ID)

        publish_calls = m.patches["_publish"].call_args_list
        error_call = next(
            (c for c in publish_calls if c.args[1] == "error"),
            None,
        )
        assert error_call is not None
        assert error_call.args[2] == -1

    def test_output_object_path_uses_job_id(self):
        from app.tasks.clip_task import process_clip_job

        with _all_mocks() as m:
            process_clip_job(FAKE_JOB_ID, FAKE_VIDEO_ID)

        upload_call = m.patches["upload_file"].call_args
        object_name = upload_call.args[0] if upload_call.args else upload_call.kwargs.get("object_name", "")
        assert FAKE_JOB_ID in object_name
        assert object_name.endswith(".mp4")
