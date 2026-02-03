import asyncio
import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import subprocess

logger = logging.getLogger(__name__)
WIN_NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == "nt" else None


def _build_atempo_filters(speed_ratio: float) -> Optional[str]:
    try:
        sr = float(speed_ratio)
    except Exception:
        return None
    if sr <= 0:
        return None
    if abs(sr - 1.0) < 0.0001:
        return None
    factors: List[float] = []
    remaining = sr
    while remaining > 2.0:
        factors.append(2.0)
        remaining = remaining / 2.0
    while remaining < 0.5:
        factors.append(0.5)
        remaining = remaining / 0.5
    factors.append(remaining)
    parts = []
    for f in factors:
        if f <= 0:
            return None
        parts.append(f"atempo={f}")
    return ",".join(parts)


async def apply_audio_speed(input_path: str, speed_ratio: float) -> Dict[str, Any]:
    if not os.path.exists(input_path):
        return {"success": False, "error": "audio_not_found"}
    filters = _build_atempo_filters(speed_ratio)
    if not filters:
        return {"success": True, "output_path": input_path, "applied": False}
    ip = Path(input_path)
    tmp_path = ip.with_name(f"{ip.stem}_speedtmp{ip.suffix}")
    ext = ip.suffix.lower()
    if ext in {".mp3"}:
        codec_args = ["-c:a", "libmp3lame", "-q:a", "2"]
    elif ext in {".wav"}:
        codec_args = ["-c:a", "pcm_s16le"]
    else:
        codec_args = ["-c:a", "aac", "-b:a", "192k"]
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(ip),
        "-filter:a", filters,
        "-vn",
        *codec_args,
        str(tmp_path),
    ]
    kwargs = {"creationflags": WIN_NO_WINDOW} if os.name == "nt" else {}
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        **kwargs
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
        return {"success": False, "error": stderr.decode(errors="ignore")}
    try:
        os.replace(str(tmp_path), str(ip))
    except Exception:
        return {"success": False, "error": "audio_replace_failed"}
    return {"success": True, "output_path": input_path, "applied": True}
