from pathlib import Path
import subprocess

import pytest

from modules.ffmpeg_utils import resolve_ffmpeg_bin, resolve_ffprobe_bin
from modules.video_processor import (
    VideoProcessor,
    _ffmpeg_concat_file_line,
    _is_nonempty_file,
)


def test_ffmpeg_concat_file_line_escapes_single_quotes():
    assert _ffmpeg_concat_file_line("folder/a'b.mp4") == "file 'folder/a'\\''b.mp4'"


def test_is_nonempty_file(tmp_path: Path):
    missing = tmp_path / "missing.mp4"
    empty = tmp_path / "empty.mp4"
    filled = tmp_path / "filled.mp4"
    empty.touch()
    filled.write_bytes(b"video")

    assert not _is_nonempty_file(missing)
    assert not _is_nonempty_file(empty)
    assert _is_nonempty_file(filled)


def test_concat_diagnostics_are_isolated_by_task():
    processor = VideoProcessor()
    processor._set_concat_error(
        "first",
        scope="merge_videos",
        project_id="project-a",
        task_id="task-1",
    )
    processor._set_concat_error(
        "second",
        scope="merge_videos",
        project_id="project-a",
        task_id="task-2",
    )

    assert processor.get_last_concat_error(
        scope="merge_videos",
        project_id="project-a",
        task_id="task-1",
    ) == "first"
    assert processor.get_last_concat_error(
        scope="merge_videos",
        project_id="project-a",
        task_id="task-2",
    ) == "second"


@pytest.mark.asyncio
async def test_concat_videos_reencodes_mixed_inputs(tmp_path: Path):
    ffmpeg = resolve_ffmpeg_bin()
    ffprobe = resolve_ffprobe_bin()
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg and ffprobe are required")

    landscape = tmp_path / "landscape.mp4"
    portrait = tmp_path / "portrait.mp4"
    output = tmp_path / "merged.mp4"

    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=160x90:r=24:d=0.5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=0.5",
            "-c:v",
            "mpeg4",
            "-c:a",
            "aac",
            "-shortest",
            "-y",
            str(landscape),
        ],
        check=True,
    )
    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=90x160:r=30:d=0.5",
            "-c:v",
            "mpeg4",
            "-an",
            "-y",
            str(portrait),
        ],
        check=True,
    )

    processor = VideoProcessor()
    ok = await processor.concat_videos(
        [str(landscape), str(portrait)],
        str(output),
        force_reencode=True,
    )

    assert ok, processor.last_concat_error
    assert _is_nonempty_file(output)

    probe = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,width,height",
            "-of",
            "default=nw=1",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "codec_type=video" in probe.stdout
    assert "width=160" in probe.stdout
    assert "height=160" in probe.stdout
    assert "codec_type=audio" in probe.stdout


@pytest.mark.asyncio
async def test_concat_videos_uses_fast_path_for_compatible_inputs(tmp_path: Path):
    ffmpeg = resolve_ffmpeg_bin()
    ffprobe = resolve_ffprobe_bin()
    if not ffmpeg or not ffprobe:
        pytest.skip("ffmpeg and ffprobe are required")

    inputs = []
    for index, color in enumerate(("red", "blue")):
        path = tmp_path / f"clip_{index}.mp4"
        subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=160x90:r=24:d=0.35",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={440 + index * 110}:duration=0.35",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                "-y",
                str(path),
            ],
            check=True,
        )
        inputs.append(str(path))

    output = tmp_path / "merged.mp4"
    processor = VideoProcessor()
    ok = await processor.concat_videos(inputs, str(output))

    assert ok, processor.last_concat_error
    assert _is_nonempty_file(output)
    assert "-f concat" in " ".join(processor.last_concat_cmd or [])
    assert not list(tmp_path.glob(".concat_*"))
