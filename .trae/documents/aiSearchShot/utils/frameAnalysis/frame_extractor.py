import os
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List


def _get_ffmpeg_bin() -> str:
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        return get_ffmpeg_exe()
    except ModuleNotFoundError:
        import shutil

        ffmpeg_bin = shutil.which("ffmpeg")
        if ffmpeg_bin:
            return ffmpeg_bin
        raise ModuleNotFoundError(
            "缺少 imageio_ffmpeg 且系统中未找到 ffmpeg。请执行 `pip install imageio-ffmpeg` 或安装系统 ffmpeg。"
        )


def extract_middle_frame(
    video_path: str,
    shot: Dict[str, Any],
    out_dir: str,
    *,
    filename_prefix: str = "shot",
    image_ext: str = ".jpg",
    overwrite: bool = False,
) -> str:
    """
    从镜头(start/end, 秒)截取中间帧图片并返回图片路径。
    """
    start = float(shot.get("start", 0.0) or 0.0)
    end = float(shot.get("end", 0.0) or 0.0)
    if end <= start:
        ts = start
    else:
        ts = (start + end) / 2.0

    shot_id = shot.get("shot_id")
    try:
        shot_id_int: Optional[int] = int(shot_id) if shot_id is not None else None
    except Exception:
        shot_id_int = None

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if shot_id_int is not None:
        out_path = os.path.join(out_dir, f"{filename_prefix}_{shot_id_int:03d}{image_ext}")
    else:
        out_path = os.path.join(out_dir, f"{filename_prefix}_{ts:.3f}{image_ext}")

    if (not overwrite) and os.path.exists(out_path):
        return out_path

    ffmpeg_bin = _get_ffmpeg_bin()
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


def extract_quarter_frames(
    video_path: str,
    shot: Dict[str, Any],
    out_dir: str,
    *,
    filename_prefix: str = "shot",
    image_ext: str = ".jpg",
    overwrite: bool = False,
) -> List[str]:
    """
    从镜头(start/end, 秒)分别在 1/4 与 3/4 位置抽帧，返回两张图片路径（按时间顺序）。
    - 当 end <= start 时，两帧都回退为 start（但仍返回两个路径，方便上游统一处理）。
    """
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

    ffmpeg_bin = _get_ffmpeg_bin()

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

    p1 = _extract_one(ts1, out_path_1)
    p2 = _extract_one(ts2, out_path_2)
    return [p1, p2]

