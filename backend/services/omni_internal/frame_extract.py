import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.ffmpeg_utils import get_ffmpeg_cuda_prefix, resolve_ffmpeg_bin
from modules.subprocess_no_console import run_no_console


logger = logging.getLogger(__name__)
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

        def _build_cmd(hwaccel_prefix: tuple[str, ...] = ()) -> List[str]:
            return [
                ffmpeg_bin,
                "-loglevel",
                "error",
                "-y",
                *hwaccel_prefix,
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

        def _run_cmd(cmd: List[str]) -> subprocess.CompletedProcess[bytes]:
            return run_no_console(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        cuda_prefix = get_ffmpeg_cuda_prefix()
        if cuda_prefix:
            logger.info("[Omni][frame_extract][GPU] ffmpeg hwaccel=cuda out=%s", out_path)
            proc = _run_cmd(_build_cmd(cuda_prefix))
            if proc.returncode == 0 and os.path.exists(out_path):
                return out_path
            msg = (proc.stderr or b"")[:500].decode("utf-8", errors="ignore").strip()
            logger.warning("[Omni][frame_extract][GPU->CPU] CUDA hwaccel 失败，回退 CPU: %s", msg or f"rc={proc.returncode}")

        logger.info("[Omni][frame_extract][CPU] ffmpeg hwaccel=off out=%s", out_path)
        proc = _run_cmd(_build_cmd(()))
        if proc.returncode != 0 or not os.path.exists(out_path):
            raise subprocess.CalledProcessError(proc.returncode, proc.args, stderr=proc.stderr)
        return out_path

    return [_extract_one(ts1, out_path_1), _extract_one(ts2, out_path_2)]


def extract_third_frames(
    video_path: str,
    shot: Dict[str, Any],
    out_dir: str,
    *,
    filename_prefix: str = "shot",
    image_ext: str = ".jpg",
    overwrite: bool = False,
) -> List[str]:
    """每个镜头在 1/3、2/3 时间点各抽一帧，共两帧。"""
    start = float(shot.get("start", 0.0) or 0.0)
    end = float(shot.get("end", 0.0) or 0.0)
    if end <= start:
        ts1 = start
        ts2 = start
    else:
        dur = end - start
        ts1 = start + dur * (1.0 / 3.0)
        ts2 = start + dur * (2.0 / 3.0)

    shot_id = shot.get("shot_id")
    try:
        shot_id_int: Optional[int] = int(shot_id) if shot_id is not None else None
    except Exception:
        shot_id_int = None

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if shot_id_int is not None:
        out_path_1 = os.path.join(out_dir, f"{filename_prefix}_{shot_id_int:03d}_t1{image_ext}")
        out_path_2 = os.path.join(out_dir, f"{filename_prefix}_{shot_id_int:03d}_t2{image_ext}")
    else:
        out_path_1 = os.path.join(out_dir, f"{filename_prefix}_{ts1:.3f}_t1{image_ext}")
        out_path_2 = os.path.join(out_dir, f"{filename_prefix}_{ts2:.3f}_t2{image_ext}")

    ffmpeg_bin = resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        raise RuntimeError(
            "缺少 imageio_ffmpeg 且系统中未找到 ffmpeg。请执行 `pip install imageio-ffmpeg` 或安装系统 ffmpeg。"
        )

    def _extract_one(ts: float, out_path: str) -> str:
        if (not overwrite) and os.path.exists(out_path):
            return out_path

        def _build_cmd(hwaccel_prefix: tuple[str, ...] = ()) -> List[str]:
            return [
                ffmpeg_bin,
                "-loglevel",
                "error",
                "-y",
                *hwaccel_prefix,
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

        def _run_cmd(cmd: List[str]) -> subprocess.CompletedProcess[bytes]:
            return run_no_console(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        cuda_prefix = get_ffmpeg_cuda_prefix()
        if cuda_prefix:
            logger.info("[Omni][frame_extract][GPU] ffmpeg hwaccel=cuda out=%s", out_path)
            proc = _run_cmd(_build_cmd(cuda_prefix))
            if proc.returncode == 0 and os.path.exists(out_path):
                return out_path
            msg = (proc.stderr or b"")[:500].decode("utf-8", errors="ignore").strip()
            logger.warning("[Omni][frame_extract][GPU->CPU] CUDA hwaccel 失败，回退 CPU: %s", msg or f"rc={proc.returncode}")

        logger.info("[Omni][frame_extract][CPU] ffmpeg hwaccel=off out=%s", out_path)
        proc = _run_cmd(_build_cmd(()))
        if proc.returncode != 0 or not os.path.exists(out_path):
            raise subprocess.CalledProcessError(proc.returncode, proc.args, stderr=proc.stderr)
        return out_path

    return [_extract_one(ts1, out_path_1), _extract_one(ts2, out_path_2)]


def extract_middle_frame(
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
        ts = start
    else:
        dur = end - start
        ts = start + dur * 0.5

    shot_id = shot.get("shot_id")
    try:
        shot_id_int: Optional[int] = int(shot_id) if shot_id is not None else None
    except Exception:
        shot_id_int = None

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if shot_id_int is not None:
        out_path = os.path.join(out_dir, f"{filename_prefix}_{shot_id_int:03d}_mid{image_ext}")
    else:
        out_path = os.path.join(out_dir, f"{filename_prefix}_{ts:.3f}_mid{image_ext}")

    ffmpeg_bin = resolve_ffmpeg_bin()
    if not ffmpeg_bin:
        raise RuntimeError(
            "缺少 imageio_ffmpeg 且系统中未找到 ffmpeg。请执行 `pip install imageio-ffmpeg` 或安装系统 ffmpeg。"
        )

    if (not overwrite) and os.path.exists(out_path):
        return [out_path]

    def _build_cmd(hwaccel_prefix: tuple[str, ...] = ()) -> List[str]:
        return [
            ffmpeg_bin,
            "-loglevel",
            "error",
            "-y",
            *hwaccel_prefix,
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

    def _run_cmd(cmd: List[str]) -> subprocess.CompletedProcess[bytes]:
        return run_no_console(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    cuda_prefix = get_ffmpeg_cuda_prefix()
    if cuda_prefix:
        logger.info("[Omni][frame_extract][GPU] ffmpeg hwaccel=cuda out=%s", out_path)
        proc = _run_cmd(_build_cmd(cuda_prefix))
        if proc.returncode == 0 and os.path.exists(out_path):
            return [out_path]
        msg = (proc.stderr or b"")[:500].decode("utf-8", errors="ignore").strip()
        logger.warning("[Omni][frame_extract][GPU->CPU] CUDA hwaccel 失败，回退 CPU: %s", msg or f"rc={proc.returncode}")

    logger.info("[Omni][frame_extract][CPU] ffmpeg hwaccel=off out=%s", out_path)
    proc = _run_cmd(_build_cmd(()))
    if proc.returncode != 0 or not os.path.exists(out_path):
        raise subprocess.CalledProcessError(proc.returncode, proc.args, stderr=proc.stderr)
    return [out_path]
