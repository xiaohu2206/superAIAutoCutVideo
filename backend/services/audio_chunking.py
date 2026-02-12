from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


logger = logging.getLogger(__name__)
WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


@dataclass(frozen=True)
class AudioChunkPlan:
    chunk_id: str
    core_start_ms: int
    core_end_ms: int
    start_ms: int
    end_ms: int


async def get_audio_duration_ms(audio_path: Path) -> Optional[int]:
    try:
        cmd_a = [
            "ffprobe", "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=duration",
            "-of", "default=nk=1:nw=1",
            str(audio_path),
        ]
        proc_a = await asyncio.create_subprocess_exec(
            *cmd_a,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=WIN_NO_WINDOW,
        )
        out_a, _ = await proc_a.communicate()
        if proc_a.returncode == 0:
            try:
                sec = float(out_a.decode(errors="ignore").strip())
                if sec > 0:
                    return int(sec * 1000)
            except Exception:
                pass
        cmd_f = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nk=1:nw=1",
            str(audio_path),
        ]
        proc_f = await asyncio.create_subprocess_exec(
            *cmd_f,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=WIN_NO_WINDOW,
        )
        out_f, _ = await proc_f.communicate()
        if proc_f.returncode == 0:
            try:
                sec = float(out_f.decode(errors="ignore").strip())
                if sec > 0:
                    return int(sec * 1000)
            except Exception:
                return None
        return None
    except Exception:
        return None


def plan_audio_chunks(
    total_ms: int,
    *,
    base_ms: int = 5 * 60 * 1000,
    min_ms: int = 2 * 60 * 1000,
    max_ms: int = 7 * 60 * 1000,
    overlap_ms: int = 30 * 1000,
) -> List[AudioChunkPlan]:
    if total_ms <= 0:
        return []

    if total_ms <= max_ms:
        return [AudioChunkPlan(
            chunk_id="chunk_0001",
            core_start_ms=0,
            core_end_ms=total_ms,
            start_ms=0,
            end_ms=total_ms,
        )]

    cores: List[tuple[int, int]] = []
    start = 0
    while start < total_ms:
        remaining = total_ms - start
        if remaining <= max_ms and remaining >= min_ms:
            end = total_ms
        else:
            end = min(start + base_ms, total_ms)
        if end <= start:
            break
        cores.append((start, end))
        start = end

    if len(cores) >= 2:
        last_len = cores[-1][1] - cores[-1][0]
        if last_len < min_ms:
            prev_start, _prev_end = cores[-2]
            merged_len = total_ms - prev_start
            if merged_len <= max_ms:
                cores[-2] = (prev_start, total_ms)
                cores.pop()
            else:
                new_last_start = max(prev_start + min_ms, total_ms - min_ms)
                cores[-2] = (prev_start, new_last_start)
                cores[-1] = (new_last_start, total_ms)

    plans: List[AudioChunkPlan] = []
    n = len(cores)
    for i, (core_s, core_e) in enumerate(cores, start=1):
        s = core_s - overlap_ms if i > 1 else core_s
        e = core_e + overlap_ms if i < n else core_e
        s = max(0, s)
        e = min(total_ms, e)
        if e <= s:
            continue
        plans.append(AudioChunkPlan(
            chunk_id=f"chunk_{i:04d}",
            core_start_ms=core_s,
            core_end_ms=core_e,
            start_ms=s,
            end_ms=e,
        ))
    return plans


async def cut_audio_mp3(
    input_mp3: Path,
    output_mp3: Path,
    *,
    start_ms: int,
    end_ms: int,
) -> bool:
    try:
        if end_ms <= start_ms:
            return False
        start_sec = max(0.0, start_ms / 1000.0)
        dur_sec = max(0.01, (end_ms - start_ms) / 1000.0)
        output_mp3.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            "-ss", str(start_sec),
            "-t", str(dur_sec),
            "-i", str(input_mp3),
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "2",
            "-y", str(output_mp3),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=WIN_NO_WINDOW,
        )
        _out, err = await proc.communicate()
        if proc.returncode == 0 and output_mp3.exists():
            return True
        logger.error(f"切分音频失败: {err.decode(errors='ignore')}")
        return False
    except Exception as e:
        logger.error(f"切分音频出错: {e}")
        return False

