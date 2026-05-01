import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.ffmpeg_utils import resolve_ffmpeg_bin


def extract_quarter_frames(
    video_path: str,
    shot: Dict[str, Any],
    out_dir: str,
    *,
    filename_prefix: str = "shot",
    image_ext: str = ".jpg",
    overwrite: bool = False,
) -> List[str]:
    start = float(shot.get("start", 0.0) or 0.0)
    end = float(shot.get("end", 0.0) or 0.0)
    if end <= start:
        ts1 = start
        ts2 = start
    else:
        dur = end - start
        ts1 = start + dur * 0.25
        ts2 = start + dur * 0.75

    shot_id = shot.get("shot_id")
    try:
        shot_id_int: Optional[int] = int(shot_id) if shot_id is not None else None
    except Exception:
        shot_id_int = None

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if shot_id_int is not None:
        out_path_1 = os.path.join(out_dir, f"{filename_prefix}_{shot_id_int:03d}_q1{image_ext}")
        out_path_2 = os.path.join(out_dir, f"{filename_prefix}_{shot_id_int:03d}_q3{image_ext}")
    else:
        out_path_1 = os.path.join(out_dir, f"{filename_prefix}_{ts1:.3f}_q1{image_ext}")
        out_path_2 = os.path.join(out_dir, f"{filename_prefix}_{ts2:.3f}_q3{image_ext}")

    ffmpeg_bin = resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        raise RuntimeError(
            "缺少 imageio_ffmpeg 且系统中未找到 ffmpeg。请执行 `pip install imageio-ffmpeg` 或安装系统 ffmpeg。"
        )

    def _extract_one(ts: float, out_path: str) -> str:
        if (not overwrite) and os.path.exists(out_path):
            return out_path
        cmd = [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{ts:.3f}",
            "-i",
            video_path,
            "-frames:v",
            "1",
            "-q:v",
            "2",
            out_path,
        ]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return out_path

    return [_extract_one(ts1, out_path_1), _extract_one(ts2, out_path_2)]
