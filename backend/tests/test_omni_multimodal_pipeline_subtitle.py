import asyncio
from pathlib import Path
from types import SimpleNamespace

from services import omni_multimodal_pipeline_service as omni_module
from modules.subtitle_utils import SUBTITLE_PARSER_VERSION, compress_srt_content, parse_srt


def test_manual_subtitle_skips_asr_before_pipeline(monkeypatch):
    project = SimpleNamespace(
        project_type="omni",
        subtitle_path="/uploads/subtitles/manual.srt",
        subtitle_source="user",
        subtitle_status="extracting",
    )
    monkeypatch.setattr(omni_module.projects_store, "get_project", lambda _project_id: project)

    async def acquire(*_args, **_kwargs):
        return None

    async def release(*_args, **_kwargs):
        return None

    async def unexpected_extract(*_args, **_kwargs):
        raise AssertionError("manual subtitle must not trigger ASR")

    async def submit_pipeline(*_args, **_kwargs):
        return {"task_id": "pipeline-task", "status": "pending"}

    monkeypatch.setattr(omni_module.project_task_queue, "acquire", acquire)
    monkeypatch.setattr(omni_module.project_task_queue, "release", release)
    monkeypatch.setattr(omni_module.extract_subtitle_service, "extract_subtitle", unexpected_extract)
    monkeypatch.setattr(omni_module.omni_multimodal_pipeline_service, "submit_pipeline", submit_pipeline)

    result = asyncio.run(
        omni_module.omni_multimodal_pipeline_service.extract_subtitle_if_needed_then_submit_pipeline(
            "project-1"
        )
    )

    assert result["subtitle_extracted"] is False
    assert result["subtitle"] is None
    assert result["pipeline"]["task_id"] == "pipeline-task"


def test_step1_cache_is_invalidated_when_subtitle_changes(tmp_path: Path):
    video = tmp_path / "video.mp4"
    subtitle = tmp_path / "subtitle.srt"
    video.write_bytes(b"video")
    subtitle.write_text("first subtitle", encoding="utf-8")

    snapshot = {
        "shots": [{"shot_id": 1}],
        "subtitle_parser_version": SUBTITLE_PARSER_VERSION,
        "step1_sources": {
            "video": omni_module._path_stat_fingerprint(video),
            "subtitle": omni_module._path_stat_fingerprint(subtitle),
        },
    }
    assert omni_module._step1_snapshot_matches_sources(snapshot, video, subtitle)

    subtitle.write_text("a different manual subtitle", encoding="utf-8")

    assert not omni_module._step1_snapshot_matches_sources(snapshot, video, subtitle)


def test_step2_cache_requires_matching_step1_sources():
    old_payload = {
        "subtitle_parser_version": SUBTITLE_PARSER_VERSION,
        "step1_sources": {
            "video": {"size": 10, "mtime_ns": 1},
            "subtitle": {"size": 20, "mtime_ns": 2},
        }
    }
    new_step1 = {
        "subtitle_parser_version": SUBTITLE_PARSER_VERSION,
        "step1_sources": {
            "video": {"size": 10, "mtime_ns": 1},
            "subtitle": {"size": 30, "mtime_ns": 3},
        }
    }

    assert not omni_module._step1_sources_equal(old_payload, new_step1)


def test_manual_subtitle_with_single_digit_hour_and_nul_is_parsed(tmp_path: Path):
    subtitle = tmp_path / "manual.srt"
    subtitle.write_text(
        "[0:00:09,300-0:00:10,900] 我正在路上\x00\n",
        encoding="utf-8",
    )

    assert parse_srt(subtitle) == [
        {
            "id": "1",
            "start_time": 9.3,
            "end_time": 10.9,
            "text": "我正在路上",
            "subtitle": "我正在路上",
        }
    ]


def test_uploaded_srt_timestamps_are_normalized():
    source = "1\n0:00:09,300 --> 0:00:10,900\n我正在路上\x00\n"

    assert compress_srt_content(source) == "[00:00:09,300-00:00:10,900] 我正在路上\n"
